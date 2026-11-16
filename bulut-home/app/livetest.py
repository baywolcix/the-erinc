"""GERÇEK API ile düşük maliyetli canlı testler. Yalnızca kullanıcı açıkça başlatınca çalışır (CLI veya arayüz onayı).

- Senaryolar geçici bir veritabanında çalışır (gerçek hafıza/görevlerin kirlenmez).
- Model çağrılarının maliyeti ANA veritabanına yazılır (aylık bütçe bunları görür).
- Tek çalıştırma için sert üst sınır: LIVE_MAX_USD. Bütçe koruması ayrıca geçerlidir.
- Sağlayıcı yoksa "çalıştırılmadı" döner; hiçbir zaman başarılı gibi raporlamaz.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
import unicodedata
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from . import agent, memory
from .config import Settings
from .db import Database, log_activity, now_iso
from .llm.router import BudgetError, LLMRouter, NoProviderError, ProvidersFailed
from .persona import build_system
from .tools import CHAT_TOOLS, ToolContext

LIVE_MAX_USD = 0.05
CODEWORD = "LACIVERT-PUSULA-7"
TASK_TITLE = "Canlı test: kapı sesi kontrolü"
SCENARIOS = ("chat", "memory_search", "task_create")


def _norm(s: str) -> str:
    s = s.replace("İ", "I").replace("ı", "i")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


def estimate_max_usd(router: LLMRouter) -> float | None:
    from .llm.pricing import worst_case_usd
    r = router.chain("fast")[0]
    p = router.providers.get(r.provider)
    price = p.price(p.resolve_model(r.model) if hasattr(p, "resolve_model") else r.model) if p else None
    if price is None:
        return None
    # chat: 1 çağrı; hafıza ve görev: ~2'şer çağrı (araç + son yanıt) → 5 çağrı, ~4K giriş, 4096 çıktı üst sınırı
    return min(LIVE_MAX_USD, 5 * worst_case_usd(price, 4000, 4096))


class _LiveRouter(LLMRouter):
    """Kayıtları geçici DB'ye yazar ama bütçeyi ANA DB'nin aylık harcamasına göre denetler."""

    def __init__(self, tmp_db: Database, main_db: Database, base: LLMRouter):
        super().__init__(tmp_db, base.settings, base.providers)
        self.main_db = main_db

    def month_spend_usd(self) -> dict:
        main = LLMRouter.month_spend_usd(type("R", (), {"db": self.main_db})())
        mine = LLMRouter.month_spend_usd(self)
        return {k: main[k] + mine[k] for k in main}


def _copy_calls(src: Database, dst: Database) -> None:
    rows = src.query("SELECT provider, model, purpose, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
                     "cost_usd, cost_known, ok, error, latency_ms, created_at FROM llm_calls ORDER BY id")
    if not rows:
        return
    cols = list(rows[0])
    with dst.tx() as t:
        t.executemany(f"INSERT INTO llm_calls({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                      [tuple(r[c] for c in cols) for r in rows])


def _calls_cost(db: Database, ids: list[int]) -> tuple[float, int, int, str]:
    if not ids:
        return 0.0, 0, 0, ""
    q = ",".join("?" * len(ids))
    r = db.one(f"SELECT COALESCE(SUM(cost_usd),0) AS usd, SUM(input_tokens) AS i, SUM(output_tokens) AS o, "
               f"GROUP_CONCAT(DISTINCT provider || ':' || model) AS m FROM llm_calls WHERE id IN ({q})", tuple(ids))
    return r["usd"] or 0.0, r["i"] or 0, r["o"] or 0, r["m"] or ""


async def run_live(settings: Settings, main_db: Database, router: LLMRouter, scenarios=SCENARIOS) -> dict:
    started = now_iso()
    report: dict = {"started_at": started, "real_api": True, "ran": False, "results": [], "total_cost_usd": 0.0}
    usable = [r for r in router.chain("fast") if router.providers.get(r.provider) and router.providers[r.provider].available()]
    if not usable:
        report.update(real_api=False, reason="Hiçbir model sağlayıcısının anahtarı ayarlı değil; canlı test ÇALIŞTIRILMADI.")
        return report
    if not settings.usd_try_rate:
        report.update(real_api=False, reason="BULUT_USD_TRY_RATE boş; bütçe korunamayacağı için canlı test ÇALIŞTIRILMADI.")
        return report
    report["ran"] = True
    report["route"] = str(usable[0])
    # Dürüstlük: yalnızca gerçek API istemcisi sınıfları "gerçek API" sayılır (testlerdeki sahte sağlayıcı sayılmaz)
    from .llm.providers import AnthropicProvider, OpenAICompatProvider
    report["real_api"] = isinstance(router.providers[usable[0].provider], (AnthropicProvider, OpenAICompatProvider))
    tmp = Path(tempfile.mkdtemp(prefix="bulut-live-"))
    tdb = Database(tmp / "live.db")
    tdb.init()
    real_router = router
    router = _LiveRouter(tdb, main_db, real_router)
    spent = 0.0
    try:
        for name in scenarios:
            if spent >= LIVE_MAX_USD:
                report["results"].append({"name": name, "status": "SKIPPED", "detail": "Canlı test maliyet tavanına ulaşıldı"})
                continue
            t0 = time.monotonic()
            res: dict = {"name": name}
            ids: list[int] = []
            try:
                if name == "chat":
                    ar = await agent.run(router, ToolContext(tdb, "livetest:chat"),
                                         system=build_system([], "", [], datetime.now().strftime("%Y-%m-%d")),
                                         messages=[{"role": "user", "content": "Bu bir bağlantı testi. Yalnızca 'BULUT hazır' yaz."}],
                                         tier="fast", purpose="livetest:chat", allowed_tools=[])
                    ids = ar.llm_call_ids
                    text = ar.text
                    res.update(status="PASS" if text.strip() else "FAIL", answer=text[:300],
                               detail="Model yanıt verdi" if text.strip() else "Boş yanıt")
                elif name == "memory_search":
                    memory.add(tdb, f"Canlı test için kod kelime: {CODEWORD}", kind="fact", source="livetest")
                    ctx = ToolContext(tdb, "livetest:memory")
                    ar = await agent.run(router, ctx, system=build_system([], "", [], datetime.now().strftime("%Y-%m-%d")),
                                         messages=[{"role": "user", "content": "Hafızanda canlı test için kaydedilmiş bir kod kelime var. "
                                                    "search_memory aracıyla bul ve yalnızca kod kelimeyi yaz."}],
                                         tier="fast", purpose="livetest:memory", allowed_tools=CHAT_TOOLS)
                    ids = ar.llm_call_ids
                    used = [e["name"] for e in ar.tool_events]
                    found = _norm(CODEWORD) in _norm(ar.text)
                    ok = "search_memory" in used and found
                    res.update(status="PASS" if ok else "FAIL", answer=ar.text[:300], tools=used,
                               detail=("search_memory çağrıldı ve kod kelime bulundu" if ok else
                                       f"araçlar={used or 'hiç'}, kod kelime yanıtta {'var' if found else 'yok'}"))
                elif name == "task_create":
                    ctx = ToolContext(tdb, "livetest:task")
                    projects = tdb.query("SELECT slug, name, status, description FROM projects")
                    ar = await agent.run(router, ctx, system=build_system([], "", projects, datetime.now().strftime("%Y-%m-%d")),
                                         messages=[{"role": "user", "content": f"Yan Daire projesine '{TASK_TITLE}' başlıklı, öncelik 3, "
                                                    "manual türünde bir görev oluştur. Başka bir şey yapma."}],
                                         tier="fast", purpose="livetest:task", allowed_tools=CHAT_TOOLS)
                    ids = ar.llm_call_ids
                    row = tdb.one("SELECT t.title, t.priority, t.kind, p.slug FROM tasks t LEFT JOIN projects p ON p.id=t.project_id "
                                  "ORDER BY t.id DESC LIMIT 1")
                    ok = bool(row) and _norm(TASK_TITLE)[:20] in _norm(row["title"]) and row["slug"] == "yan-daire"
                    res.update(status="PASS" if ok else "FAIL", answer=ar.text[:300], tools=[e["name"] for e in ar.tool_events],
                               task=row, detail="Görev doğru projede oluşturuldu" if ok else f"Beklenen görev yok: {row}")
            except (BudgetError, NoProviderError, ProvidersFailed) as e:
                res.update(status="ERROR", detail=f"{type(e).__name__}: {e}")
            except Exception as e:  # noqa: BLE001
                res.update(status="ERROR", detail=f"{type(e).__name__}: {e}")
            usd, i, o, models = _calls_cost(tdb, ids)
            spent += usd
            res.update(cost_usd=round(usd, 6), input_tokens=i, output_tokens=o, model=models, llm_calls=len(ids),
                       seconds=round(time.monotonic() - t0, 1))
            report["results"].append(res)
    finally:
        _copy_calls(tdb, main_db)  # maliyet ana bütçeye
        shutil.rmtree(tmp, ignore_errors=True)
    report["total_cost_usd"] = round(spent, 6)
    report["finished_at"] = now_iso()
    report["passed"] = sum(r["status"] == "PASS" for r in report["results"])
    report["all_passed"] = report["passed"] == len(report["results"])
    out_dir = settings.data_dir / "live_tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"live-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    report["report_file"] = path.name
    log_activity(main_db, "live_test", f"{'Canlı API' if report['real_api'] else 'SAHTE sağlayıcı ile'} testi: {report['passed']}/{len(report['results'])} geçti "
                 f"(≈${report['total_cost_usd']:.4f})", detail=json.dumps([{k: r.get(k) for k in ('name', 'status', 'detail')}
                                                                          for r in report["results"]], ensure_ascii=False),
                 level="info" if report["all_passed"] else "warn")
    return report


def list_reports(settings: Settings, limit: int = 10) -> list[dict]:
    d = settings.data_dir / "live_tests"
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("live-*.json"), reverse=True)[:limit]:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            r["report_file"] = p.name
            out.append(r)
        except (OSError, json.JSONDecodeError):
            continue
    return out


def cli_main(settings: Settings, db: Database, yes: bool = False) -> int:
    import asyncio
    from .main import build_providers
    from .redact import register
    register(settings.anthropic_api_key, settings.compat_api_key, settings.brave_api_key)
    router = LLMRouter(db, settings, build_providers(settings))
    est = estimate_max_usd(router)
    print("GERÇEK API canlı testi: sohbet, hafıza arama (araç), görev oluşturma (araç).")
    print(f"Model: {router.chain('fast')[0]}  |  En kötü durum tahmini: "
          + (f"${est:.4f} (≈{est * settings.usd_try_rate:.2f} TL)" if est and settings.usd_try_rate else "bilinmiyor")
          + f"  |  Sert tavan: ${LIVE_MAX_USD}")
    if not yes:
        if input("Devam etmek için 'evet' yaz: ").strip().lower() != "evet":
            print("İptal edildi; hiçbir çağrı yapılmadı.")
            return 2
    rep = asyncio.run(run_live(settings, db, router))
    if not rep["ran"]:
        print("ÇALIŞTIRILMADI:", rep["reason"])
        return 3
    for r in rep["results"]:
        print(f"[{r['status']:7}] {r['name']:14} {r.get('model','')}  {r.get('input_tokens',0)}+{r.get('output_tokens',0)} tok  "
              f"${r.get('cost_usd',0):.5f}  — {r.get('detail','')}")
    print(f"Toplam: {rep['passed']}/{len(rep['results'])} geçti, ≈${rep['total_cost_usd']:.5f}. Rapor: data/live_tests/{rep['report_file']}")
    return 0 if rep["all_passed"] else 1
