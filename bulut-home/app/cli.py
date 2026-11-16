"""Yönetim komutları:
  python -m app.cli set-password <kullanıcı>   parola ayarla (tüm oturumlar düşer)
  python -m app.cli backup                     veritabanı yedeği
  python -m app.cli check                      API anahtarlarını token harcamadan doğrula
  python -m app.cli status                     yapılandırma özeti (gizli değerler gösterilmez)
  python -m app.cli live-test [--yes]          GERÇEK API ile düşük maliyetli canlı test (onay ister)
"""
from __future__ import annotations

import getpass
import sys

from . import auth
from .config import load_settings
from .db import Database


def main(argv: list[str]) -> int:
    s = load_settings()
    db = Database(s.db_path)
    db.init()
    if len(argv) >= 2 and argv[0] == "set-password":
        pw = getpass.getpass("Yeni parola (en az 10 karakter): ")
        if pw != getpass.getpass("Tekrar: "):
            print("Parolalar eşleşmiyor.")
            return 1
        auth.set_password(db, argv[1], pw)
        print("Parola ayarlandı; tüm oturumlar kapatıldı.")
        return 0
    if argv[:1] == ["backup"]:
        from datetime import datetime
        dest = s.data_dir / "backups" / f"bulut-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        db.backup(dest)
        print(dest)
        return 0
    if argv[:1] == ["check"]:
        import asyncio
        from .main import build_providers
        from .llm.router import LLMRouter
        from .redact import register
        register(s.anthropic_api_key, s.compat_api_key, s.brave_api_key)
        results = asyncio.run(LLMRouter(db, s, build_providers(s)).check_providers())
        for r in results:
            print(f"{'✓' if r['ok'] else '✗'} {r['route']:40} {r['message']}")
        if not s.usd_try_rate:
            print("! BULUT_USD_TRY_RATE boş: bütçe koruması ücretli çağrılara izin vermez.")
        return 0 if any(r["ok"] for r in results) else 1
    if argv[:1] == ["status"]:
        print(f"Veri klasörü     : {s.data_dir}")
        print(f"Anthropic anahtarı: {'ayarlı' if s.anthropic_api_key else 'yok'}")
        print(f"OpenAI uyumlu     : {'ayarlı' if s.compat_api_key else 'yok'}")
        print(f"Web araması       : {'brave' if s.brave_api_key else ('searxng' if s.searxng_url else 'yok')}")
        print(f"Modeller          : hızlı={s.model_fast} akıllı={s.model_smart} yedek={','.join(s.model_fallbacks) or '-'}")
        print(f"Bütçe             : {s.monthly_budget_try:.0f} TL / ay, kur={s.usd_try_rate or 'girilmedi'}")
        return 0
    if argv[:1] == ["live-test"]:
        from .livetest import cli_main
        return cli_main(s, db, yes="--yes" in argv)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
