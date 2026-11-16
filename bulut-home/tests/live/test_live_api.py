"""GERÇEK API testleri — ücretlidir (toplam < $0.05 sert tavan). Yalnızca açıkça istendiğinde çalışır:

    BULUT_LIVE_TESTS=1 python -m pytest -m live tests/live        (anahtarlar .env'den veya ortamdan)

Önerilen yol: `python -m app.cli live-test` (onay sorar, rapor yazar).
"""
import asyncio
import os
import tempfile
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("BULUT_LIVE_TESTS") != "1", reason="Canlı API testleri kapalı (BULUT_LIVE_TESTS=1 değil)"),
]


@pytest.fixture(scope="module")
def live_report():
    from app.config import load_settings
    from app.db import Database
    from app.livetest import run_live
    from app.llm.router import LLMRouter
    from app.main import build_providers
    s = load_settings()
    if not s.anthropic_api_key and not s.compat_api_key:
        pytest.skip("API anahtarı yok")
    db = Database(s.db_path); db.init()
    rep = asyncio.run(run_live(s, db, LLMRouter(db, s, build_providers(s))))
    if not rep["ran"]:
        pytest.skip(rep["reason"])
    assert rep["real_api"] is True
    return {r["name"]: r for r in rep["results"]}


def test_live_chat(live_report):
    assert live_report["chat"]["status"] == "PASS", live_report["chat"]


def test_live_memory_search_tool(live_report):
    assert live_report["memory_search"]["status"] == "PASS", live_report["memory_search"]


def test_live_task_create_tool(live_report):
    assert live_report["task_create"]["status"] == "PASS", live_report["task_create"]
