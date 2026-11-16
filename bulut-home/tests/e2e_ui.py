"""Tarayıcı uçtan uca testi (Node Playwright + Chromium). Gerçek model çağrısı YAPMAZ; sahte sağlayıcı kullanır.

Çalıştır: python3 tests/e2e_ui.py [ekran_görüntüsü_klasörü]
"""
import asyncio
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from conftest import FakeProvider, make_settings  # noqa: E402
from app.main import create_app  # noqa: E402


def main(shots: Path | None):
    tmp = Path(tempfile.mkdtemp())
    fake = FakeProvider(replies=[
        {"text": "Kayıtlara bakıyorum.", "tools": [
            ("daily_summary", {}),
            ("create_task", {"title": "PROGRESS.md dosyasını BULUT'a bağla", "kind": "manual", "priority": 2, "project_slug": "yan-daire"}),
            ("save_memory", {"content": "Yan Daire demo sürümünü yıl sonuna yetiştirmek", "kind": "goal", "project_slug": "yan-daire"})]},
        "Bugün kayıtlı tamamlanmış iş yok. Yan Daire için ilk görevi ekledim ve hedefi not ettim.",
        "Sabah brifingi: dün tamamlanan iş yok; bugün öncelik Yan Daire PROGRESS.md bağlantısı.",
    ] + ["Tamam."] * 20)
    app = create_app(make_settings(tmp), providers={"anthropic": fake}, start_worker=False)
    token = (tmp / ".setup_token").read_text().strip()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)

    import os
    import subprocess
    env = dict(os.environ, BULUT_URL="http://127.0.0.1:8765/", SETUP_TOKEN=token, SHOTS=str(shots or ""))
    rc = subprocess.run(["node", str(Path(__file__).with_name("e2e_ui.cjs"))], env=env).returncode
    server.should_exit = True
    sys.exit(rc)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
