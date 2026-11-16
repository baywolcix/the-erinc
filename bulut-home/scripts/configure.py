#!/usr/bin/env python3
"""BULUT HOME yapılandırma sihirbazı (sunucuda, Docker DIŞINDA çalışır; yalnızca Python standart kütüphanesi).

Kullanım:
    python3 scripts/configure.py              # etkileşimli: anahtarlar, kur, bütçe, bildirimler
    python3 scripts/configure.py --show       # hangi ayarlar dolu (değerler GÖSTERİLMEZ)
    python3 scripts/configure.py --init       # .env yoksa örnekten oluştur + rastgele oturum anahtarı

Güvenlik:
- Gizli değerler getpass ile alınır (ekrana yazılmaz), hiçbir zaman ekrana/loga basılmaz.
- .env atomik yazılır ve izinleri 600 yapılır. .env Git'e girmez (.gitignore).
- Boş bırakılan alan mevcut değeri DEĞİŞTİRMEZ; silmek için "-" yaz.
"""
from __future__ import annotations

import getpass
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"

SECRET_KEYS = {"ANTHROPIC_API_KEY", "OPENAI_COMPAT_API_KEY", "BRAVE_API_KEY", "BULUT_SECRET_KEY",
               "NTFY_TOKEN", "TELEGRAM_BOT_TOKEN"}

QUESTIONS = [
    # (anahtar, açıklama, gizli mi, doğrulama regex'i veya None)
    ("ANTHROPIC_API_KEY", "Anthropic API anahtarı (console.anthropic.com → API Keys; sk-ant- ile başlar)", True, r"sk-ant-\S{20,}"),
    ("BULUT_USD_TRY_RATE", "1 USD kaç TL? (güncel kuru gir; bütçe koruması bunsuz ücretli çağrı yapmaz)", False, r"\d+([.,]\d+)?"),
    ("BULUT_MONTHLY_BUDGET_TRY", "Aylık API bütçesi (TL)", False, r"\d+([.,]\d+)?"),
    ("OPENAI_COMPAT_API_KEY", "[İsteğe bağlı] OpenAI uyumlu sağlayıcı anahtarı (DeepSeek/OpenRouter...)", True, None),
    ("BRAVE_API_KEY", "[İsteğe bağlı] Brave Search API anahtarı (web araması için)", True, None),
    ("NTFY_TOPIC", "[İsteğe bağlı] ntfy bildirim konusu (uzun ve tahmin edilemez olmalı; boşsa ntfy kapalı)", False, r"[A-Za-z0-9_\-]{12,64}"),
    ("NTFY_URL", "[İsteğe bağlı] ntfy sunucusu (varsayılan https://ntfy.sh)", False, r"https?://\S+"),
    ("NTFY_TOKEN", "[İsteğe bağlı] ntfy erişim token'ı", True, None),
    ("TELEGRAM_BOT_TOKEN", "[İsteğe bağlı] Telegram bot token'ı (@BotFather)", True, r"\d{6,12}:[A-Za-z0-9_\-]{30,}"),
    ("TELEGRAM_CHAT_ID", "[İsteğe bağlı] Telegram sohbet kimliği", False, r"-?\d{3,20}"),
    ("BULUT_PUBLIC_URL", "[İsteğe bağlı] Tailscale HTTPS adresi (bildirimden uygulamaya bağlantı için)", False, r"https://\S+"),
]


def read_env(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def parse(lines: list[str]) -> dict[str, str]:
    out = {}
    for ln in lines:
        m = re.match(r"\s*([A-Z0-9_]+)\s*=(.*)$", ln)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def write_env(path: Path, updates: dict[str, str | None]) -> None:
    """Var olan satırları yerinde günceller, yorumları korur, yeni anahtarları sona ekler. None = sil."""
    for k, v in updates.items():
        if v is not None and ("\n" in v or "\r" in v):
            raise ValueError(f"{k}: satır sonu içeremez")
    lines = read_env(path)
    done = set()
    out = []
    for ln in lines:
        m = re.match(r"\s*([A-Z0-9_]+)\s*=", ln)
        if m and m.group(1) in updates:
            k = m.group(1)
            done.add(k)
            if updates[k] is None:
                out.append(f"{k}=")
            else:
                out.append(f"{k}={updates[k]}")
        else:
            out.append(ln)
    for k, v in updates.items():
        if k not in done and v is not None:
            out.append(f"{k}={v}")
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".env.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    os.chmod(path, 0o600)


def init_env() -> bool:
    created = False
    if not ENV.exists():
        ENV.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        created = True
    os.chmod(ENV, 0o600)
    if not parse(read_env(ENV)).get("BULUT_SECRET_KEY"):
        write_env(ENV, {"BULUT_SECRET_KEY": secrets.token_urlsafe(48)})
    return created


def show() -> None:
    vals = parse(read_env(ENV))
    if not ENV.exists():
        print(".env yok. Önce: python3 scripts/configure.py --init")
        return
    mode = oct(ENV.stat().st_mode & 0o777)
    print(f".env: {ENV}  (izinler {mode}{'' if mode == '0o600' else '  ← UYARI: 600 olmalı'})")
    for k in sorted(set(vals) | {q[0] for q in QUESTIONS}):
        v = vals.get(k, "")
        if k in SECRET_KEYS:
            state = "ayarlı" if v else "boş"
        else:
            state = v if v else "boş"
        print(f"  {k:28} {state}")


def ask() -> None:
    init_env()
    cur = parse(read_env(ENV))
    updates: dict[str, str | None] = {}
    print("Boş bırakılan alan değişmez. Silmek için '-' yaz. Gizli alanlar ekranda görünmez.\n")
    for key, desc, secret, rx in QUESTIONS:
        has = bool(cur.get(key))
        hint = ("[ayarlı]" if has else "[boş]") if secret else f"[{cur.get(key) or 'boş'}]"
        while True:
            prompt = f"{desc}\n  {key} {hint}: "
            val = getpass.getpass(prompt) if secret else input(prompt)
            val = val.strip()
            if not val:
                break
            if val == "-":
                updates[key] = None
                break
            if key in ("BULUT_USD_TRY_RATE", "BULUT_MONTHLY_BUDGET_TRY"):
                val = val.replace(",", ".")
            if rx and not re.fullmatch(rx, val):
                print("  Biçim beklenene uymuyor, tekrar dene (boş bırakıp geçebilirsin).")
                continue
            updates[key] = val
            break
    if updates:
        write_env(ENV, updates)
        print(f"\n{len(updates)} ayar kaydedildi (değerler gösterilmez). İzinler: 600.")
    else:
        print("\nDeğişiklik yok.")
    print("Uygulamak için:  docker compose up -d   (ardından: docker compose exec bulut python -m app.cli check)")


def main(argv: list[str]) -> int:
    if "--show" in argv:
        show()
    elif "--init" in argv:
        print(".env oluşturuldu." if init_env() else ".env zaten var; yalnızca eksik oturum anahtarı tamamlandı.")
    else:
        ask()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
