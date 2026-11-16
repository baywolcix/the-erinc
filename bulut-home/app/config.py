"""Ortam değişkenlerinden okunan ayarlar. Gizli anahtarlar yalnızca ortamdan gelir."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Basit .env okuyucu (ek bağımlılık olmasın diye). Var olan ortam değişkenlerini ezmez."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _float_or_none(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


@dataclass
class Settings:
    data_dir: Path
    secret_key: str
    cookie_secure: bool
    anthropic_api_key: str
    compat_api_key: str
    compat_base_url: str
    compat_model: str
    compat_price_in: float | None
    compat_price_out: float | None
    model_fast: str
    model_smart: str
    model_fallbacks: list[str] = field(default_factory=list)
    monthly_budget_try: float = 400.0
    usd_try_rate: float | None = None
    worker_enabled: bool = True
    brave_api_key: str = ""
    searxng_url: str = ""
    web_daily_limit: int = 40
    web_trust_proxy_dns: bool = False
    brief_time: str = "08:30"           # yerel saat, boş = kapalı
    timezone: str = "Europe/Istanbul"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bulut.db"


def load_settings() -> Settings:
    _load_dotenv(Path(os.environ.get("BULUT_ENV_FILE", ".env")))
    data_dir = Path(os.environ.get("BULUT_DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    secret = os.environ.get("BULUT_SECRET_KEY", "")
    if not secret:
        # Kalıcı rastgele anahtar üret; Git'e girmez (data/ ignore'lu).
        key_file = data_dir / ".secret_key"
        if key_file.exists():
            secret = key_file.read_text().strip()
        else:
            import secrets
            secret = secrets.token_urlsafe(48)
            key_file.write_text(secret)
            key_file.chmod(0o600)
    return Settings(
        data_dir=data_dir,
        secret_key=secret,
        cookie_secure=os.environ.get("BULUT_COOKIE_SECURE", "0") == "1",
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        compat_api_key=os.environ.get("OPENAI_COMPAT_API_KEY", ""),
        compat_base_url=os.environ.get("OPENAI_COMPAT_BASE_URL", "").rstrip("/"),
        compat_model=os.environ.get("OPENAI_COMPAT_MODEL", ""),
        compat_price_in=_float_or_none(os.environ.get("OPENAI_COMPAT_PRICE_IN")),
        compat_price_out=_float_or_none(os.environ.get("OPENAI_COMPAT_PRICE_OUT")),
        model_fast=os.environ.get("BULUT_MODEL_FAST", "anthropic:claude-haiku-5-5"),
        model_smart=os.environ.get("BULUT_MODEL_SMART", "anthropic:claude-sonnet-5-5"),
        model_fallbacks=[s.strip() for s in os.environ.get("BULUT_MODEL_FALLBACKS", "").split(",") if s.strip()],
        monthly_budget_try=_float_or_none(os.environ.get("BULUT_MONTHLY_BUDGET_TRY")) or 400.0,
        usd_try_rate=_float_or_none(os.environ.get("BULUT_USD_TRY_RATE")),
        worker_enabled=os.environ.get("BULUT_WORKER", "1") == "1",
        brave_api_key=os.environ.get("BRAVE_API_KEY", ""),
        searxng_url=os.environ.get("SEARXNG_URL", "").rstrip("/"),
        web_daily_limit=int(_float_or_none(os.environ.get("BULUT_WEB_DAILY_LIMIT")) or 40),
        web_trust_proxy_dns=os.environ.get("BULUT_WEB_TRUST_PROXY_DNS", "0") == "1",
        brief_time=os.environ.get("BULUT_BRIEF_TIME", "08:30").strip(),
        timezone=os.environ.get("BULUT_TIMEZONE", "Europe/Istanbul"),
    )
