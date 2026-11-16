"""Model yönlendirici: katman seçimi, bütçe koruması, yedek zinciri, maliyet kaydı, döngü sınırı."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..config import Settings
from ..db import Database, now_iso, log_activity
import threading

from .pricing import cost_usd, worst_case_usd
from .providers import REFUSAL_FALLBACK, LLMResult, Provider, ProviderError

# Karmaşıklık işaretleri: bunlar geçerse akıllı katman
_SMART_HINTS = (
    "analiz", "planla", "plan çıkar", "strateji", "karşılaştır", "kod yaz", "kodla", "mimari",
    "rapor hazırla", "senaryo", "teklif yaz", "araştır", "detaylı", "ayrıntılı", "hata ayıkla", "debug",
)

MAX_CALLS_PER_HOUR = 120  # sonsuz agent döngülerine karşı sert sınır


class BudgetError(Exception):
    """Bütçe nedeniyle ücretli çağrı engellendi."""


class NoProviderError(Exception):
    """Kullanılabilir sağlayıcı yok."""


class ProvidersFailed(Exception):
    """Sağlayıcılar denendi ama hepsi hata verdi."""

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class Route:
    provider: str
    model: str

    @classmethod
    def parse(cls, spec: str) -> "Route":
        provider, _, model = spec.partition(":")
        return cls(provider.strip(), model.strip())

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


def choose_tier(text: str) -> str:
    t = text.lower()
    if len(text) > 1500 or any(h in t for h in _SMART_HINTS):
        return "smart"
    return "fast"


def month_start_utc() -> str:
    n = datetime.now(timezone.utc)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


class LLMRouter:
    def __init__(self, db: Database, settings: Settings, providers: dict[str, Provider]):
        self.db = db
        self.settings = settings
        self.providers = providers
        # Eşzamanlı istekler bütçeyi birlikte aşmasın: uçuştaki çağrıların en kötü durum maliyeti
        self._reserved_usd = 0.0
        self._reserve_lock = threading.Lock()

    # ---------- bütçe ----------
    def month_spend_usd(self) -> dict:
        row = self.db.one(
            "SELECT COALESCE(SUM(cost_usd),0) AS usd, COUNT(*) AS calls, "
            "SUM(CASE WHEN cost_known=0 THEN 1 ELSE 0 END) AS unknown "
            "FROM llm_calls WHERE created_at >= ?",
            (month_start_utc(),),
        )
        return {"usd": row["usd"] or 0.0, "calls": row["calls"] or 0, "unknown_cost_calls": row["unknown"] or 0}

    def budget_status(self) -> dict:
        s = self.month_spend_usd()
        rate = self.settings.usd_try_rate
        budget_try = self.settings.monthly_budget_try
        spent_try = s["usd"] * rate if rate else None
        return {
            "budget_try": budget_try,
            "usd_try_rate": rate,
            "spent_usd": round(s["usd"], 6),
            "spent_try": round(spent_try, 4) if spent_try is not None else None,
            "remaining_try": round(budget_try - spent_try, 4) if spent_try is not None else None,
            "calls_this_month": s["calls"],
            "unknown_cost_calls": s["unknown_cost_calls"],
            "blocked": spent_try is None or spent_try >= budget_try,
            "reason": None if rate else "USD/TRY kuru girilmedi (BULUT_USD_TRY_RATE); ücretli çağrılar kapalı.",
        }

    def _worst_usd(self, provider: Provider, model: str, est_in: int, max_out: int) -> float:
        price = provider.price(model)
        if price is None:
            raise BudgetError(f"{provider.name}:{model} için fiyat bilinmiyor; bütçe korunamayacağı için çağrı yapılmadı.")
        worst = worst_case_usd(price, est_in, max_out)
        fb = REFUSAL_FALLBACK.get(model) if provider.name == "anthropic" else None
        if fb:  # reddedilip yedek modelde yeniden çalışırsa iki çağrı da ücretlenebilir
            fb_price = provider.price(fb)
            if fb_price is None:
                raise BudgetError(f"Yedek model {fb} için fiyat bilinmiyor.")
            worst += worst_case_usd(fb_price, est_in, max_out)
        return worst

    def _reserve(self, provider: Provider, model: str, est_in: int, max_out: int) -> float:
        """Bütçeyi kontrol et ve en kötü durum tutarını ayır. Dönen tutar `_release` ile bırakılmalı."""
        rate = self.settings.usd_try_rate
        if not rate:
            raise BudgetError("USD/TRY kuru ayarlanmadı (BULUT_USD_TRY_RATE). Bütçe korunamayacağı için ücretli çağrı yapılmadı.")
        worst = self._worst_usd(provider, model, est_in, max_out)
        with self._reserve_lock:
            spent = self.month_spend_usd()["usd"]
            if (spent + self._reserved_usd + worst) * rate > self.settings.monthly_budget_try:
                raise BudgetError(
                    f"Aylık bütçe sınırı: harcanan ≈{spent * rate:.2f} TL, bu çağrı en kötü durumda ≈{worst * rate:.2f} TL"
                    + (f", süren çağrılar ≈{self._reserved_usd * rate:.2f} TL" if self._reserved_usd else "")
                    + f", sınır {self.settings.monthly_budget_try:.0f} TL."
                )
            self._reserved_usd += worst
        return worst

    def _release(self, amount: float) -> None:
        with self._reserve_lock:
            self._reserved_usd = max(0.0, self._reserved_usd - amount)

    def _check_rate(self) -> None:
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
        n = self.db.one("SELECT COUNT(*) AS n FROM llm_calls WHERE created_at >= ?", (since,))["n"]
        if n >= MAX_CALLS_PER_HOUR:
            raise BudgetError(f"Saatlik çağrı sınırı ({MAX_CALLS_PER_HOUR}) aşıldı; olası döngü engellendi.")

    # ---------- kayıt ----------
    def _record(self, route: Route, purpose: str, res: LLMResult | None, err: str | None, latency_ms: int) -> int:
        provider = self.providers.get(route.provider)
        cost = None
        if res is not None and provider is not None:
            cost = self._cost(provider, route.model, res)
        with self.db.tx() as t:
            cur = t.execute(
                "INSERT INTO llm_calls(provider,model,purpose,input_tokens,output_tokens,cache_read_tokens,"
                "cache_write_tokens,cost_usd,cost_known,ok,error,latency_ms,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    route.provider, res.model if res else route.model, purpose,
                    res.input_tokens if res else 0, res.output_tokens if res else 0,
                    res.cache_read_tokens if res else 0, res.cache_write_tokens if res else 0,
                    cost, 0 if (res is not None and cost is None) else 1,
                    1 if res else 0, err, latency_ms, now_iso(),
                ),
            )
            return cur.lastrowid

    @staticmethod
    def _cost(provider: Provider, model: str, res: LLMResult) -> float | None:
        """Yedek model devreye girdiyse her adım kendi modelinin fiyatıyla hesaplanır."""
        its = res.extra.get("iterations") if res.extra else None
        if its:
            total = 0.0
            for it in its:
                c = cost_usd(provider.price(it.get("model") or model), it["input_tokens"], it["output_tokens"],
                             it["cache_read_tokens"], it["cache_write_tokens"])
                if c is None:
                    return None
                total += c
            return total
        return cost_usd(provider.price(model), res.input_tokens, res.output_tokens,
                        res.cache_read_tokens, res.cache_write_tokens)

    # ---------- ana çağrı ----------
    def chain(self, tier: str) -> list[Route]:
        primary = self.settings.model_smart if tier == "smart" else self.settings.model_fast
        specs = [primary] + ([self.settings.model_fast] if tier == "smart" else []) + self.settings.model_fallbacks
        seen, out = set(), []
        for s in specs:
            if s and s not in seen:
                seen.add(s)
                out.append(Route.parse(s))
        return out

    async def complete(self, *, system: str, messages: list[dict], tier: str = "fast",
                       purpose: str = "chat", max_tokens: int | None = None) -> tuple[LLMResult, int]:
        self._check_rate()
        max_tokens = max_tokens or (4096 if tier == "fast" else 8192)
        est_in = (len(system) + sum(len(str(m.get("content", ""))) for m in messages)) // 3 + 50
        errors: list[str] = []
        any_retryable = False
        budget_errors: list[str] = []
        for route in self.chain(tier):
            provider = self.providers.get(route.provider)
            if provider is None or not provider.available():
                continue
            model = route.model
            if hasattr(provider, "resolve_model"):
                model = provider.resolve_model(model)
                route = Route(route.provider, model)
            try:
                reserved = self._reserve(provider, model, est_in, max_tokens)
            except BudgetError as e:
                budget_errors.append(str(e))
                continue
            effort = ("low" if tier == "fast" else "medium") if route.provider == "anthropic" else None
            t0 = time.monotonic()
            try:
                res = await provider.complete(model=model, system=system, messages=messages,
                                              max_tokens=max_tokens, effort=effort)
            except ProviderError as e:
                self._release(reserved)
                self._record(route, purpose, None, str(e)[:500], int((time.monotonic() - t0) * 1000))
                errors.append(f"{route}: {e}")
                any_retryable = any_retryable or e.retryable
                log_activity(self.db, "llm_error", f"{route} başarısız, sıradaki deneniyor", str(e)[:500], level="warn")
                continue
            except BaseException:
                self._release(reserved)
                raise
            try:
                call_id = self._record(route, purpose, res, None, int((time.monotonic() - t0) * 1000))
            finally:
                self._release(reserved)
            return res, call_id
        if errors:
            raise ProvidersFailed("Tüm sağlayıcılar başarısız: " + " | ".join(errors), any_retryable)
        if budget_errors:
            raise BudgetError(budget_errors[0])
        raise NoProviderError("Hiçbir model sağlayıcısı yapılandırılmamış. .env içinde ANTHROPIC_API_KEY veya OPENAI_COMPAT_* ayarla.")
