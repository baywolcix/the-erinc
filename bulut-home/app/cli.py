"""Yönetim komutları: python -m app.cli set-password <kullanıcı> | backup"""
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
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
