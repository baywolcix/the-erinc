"""Oturum 3: anahtar kurulumu, gizli değer maskeleme, ücretsiz sağlayıcı kontrolü, canlı test düzeneği."""
import asyncio
import importlib.util
import json
import logging
import os
import stat
from pathlib import Path

import httpx2
import pytest
from anthropic import DefaultAsyncHttpxClient

from app.db import Database, log_activity
from app.redact import RedactingFilter, redact, register
from conftest import H, FakeProvider, make_settings

ROOT = Path(__file__).resolve().parents[1]
FAKE_KEY = "sk-ant-api03-" + "A1b2C3d4" * 6


def _configure_module():
    spec = importlib.util.spec_from_file_location("configure", ROOT / "scripts" / "configure.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------------- maskeleme ----------------
@pytest.mark.no_llm
@pytest.mark.parametrize("raw", [
    f"Hata: anahtar {FAKE_KEY} reddedildi",
    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
    "x-api-key: 0123456789abcdefghij",
    "telegram 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ hata",
    "url https://api.example/x?api_key=supersecretvalue123",
])
def test_redact_patterns(raw):
    out = redact(raw)
    assert "***" in out
    for secret in (FAKE_KEY, "abcdefghijklmnopqrstuvwxyz123456", "0123456789abcdefghij", "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ", "supersecretvalue123"):
        assert secret not in out


@pytest.mark.no_llm
def test_registered_secret_masked_everywhere(tmp_path):
    register("brv-gizli-deger-XYZ")
    db = Database(tmp_path / "x.db"); db.init()
    log_activity(db, "t", "özet brv-gizli-deger-XYZ", detail=f"ayrıntı {FAKE_KEY}")
    row = db.one("SELECT summary, detail FROM activity WHERE kind='t'")
    assert "brv-gizli" not in row["summary"] and FAKE_KEY not in row["detail"]


@pytest.mark.no_llm
def test_logging_filter_masks():
    rec = logging.LogRecord("x", logging.INFO, "f", 1, "istek %s", (FAKE_KEY,), None)
    RedactingFilter().filter(rec)
    assert FAKE_KEY not in rec.getMessage()


@pytest.mark.fake_llm
def test_provider_error_with_key_is_masked_in_db(tmp_path):
    from app.llm.providers import ProviderError
    from app.llm.router import LLMRouter, ProvidersFailed

    class Leaky(FakeProvider):
        async def complete(self, **kw):
            raise ProviderError(f"401 invalid x-api-key {FAKE_KEY}")
    s = make_settings(tmp_path)
    db = Database(s.db_path); db.init()
    with pytest.raises(ProvidersFailed) as e:
        asyncio.run(LLMRouter(db, s, {"anthropic": Leaky()}).complete(system="s", messages=[{"role": "user", "content": "x"}]))
    assert FAKE_KEY not in str(e.value)
    assert FAKE_KEY not in db.one("SELECT error FROM llm_calls")["error"]
    assert all(FAKE_KEY not in (r["detail"] or "") for r in db.query("SELECT detail FROM activity"))


# ---------------- .env sihirbazı ----------------
@pytest.mark.no_llm
def test_write_env_preserves_comments_and_perms(tmp_path):
    m = _configure_module()
    env = tmp_path / ".env"
    env.write_text("# yorum\nANTHROPIC_API_KEY=\nBULUT_USD_TRY_RATE=40\n")
    m.write_env(env, {"ANTHROPIC_API_KEY": FAKE_KEY, "NTFY_TOPIC": "bulut-abc123def456"})
    text = env.read_text()
    assert text.startswith("# yorum\n") and f"ANTHROPIC_API_KEY={FAKE_KEY}" in text and "NTFY_TOPIC=bulut-abc123def456" in text
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    m.write_env(env, {"ANTHROPIC_API_KEY": None})
    assert "ANTHROPIC_API_KEY=\n" in env.read_text()
    with pytest.raises(ValueError):
        m.write_env(env, {"X": "a\nINJECT=1"})


@pytest.mark.no_llm
def test_show_never_prints_secret(tmp_path, capsys, monkeypatch):
    m = _configure_module()
    env = tmp_path / ".env"
    env.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\nBULUT_USD_TRY_RATE=41.5\n")
    os.chmod(env, 0o600)
    monkeypatch.setattr(m, "ENV", env)
    m.show()
    out = capsys.readouterr().out
    assert FAKE_KEY not in out and "ayarlı" in out and "41.5" in out


@pytest.mark.no_llm
def test_init_generates_secret_key(tmp_path, monkeypatch):
    m = _configure_module()
    monkeypatch.setattr(m, "ENV", tmp_path / ".env")
    monkeypatch.setattr(m, "EXAMPLE", ROOT / ".env.example")
    assert m.init_env() is True
    vals = m.parse(m.read_env(tmp_path / ".env"))
    assert len(vals["BULUT_SECRET_KEY"]) > 40 and stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600


@pytest.mark.no_llm
def test_env_and_data_are_gitignored():
    gi = (ROOT / ".gitignore").read_text()
    assert ".env" in gi.split() and "data/" in gi.split()


# ---------------- ücretsiz sağlayıcı kontrolü ----------------
@pytest.mark.sdk_http
def test_anthropic_check_uses_models_api_without_tokens():
    from app.llm.providers import AnthropicProvider
    seen = []

    def handler(req):
        seen.append((req.method, req.url.path))
        auth = req.headers.get("x-api-key", "") + req.headers.get("authorization", "")
        if "bad" in auth:
            return httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid"}})
        return httpx2.Response(200, json={"type": "model", "id": "claude-haiku-5-5", "display_name": "Haiku", "created_at": "2026-01-01T00:00:00Z"})
    ok = asyncio.run(AnthropicProvider("sk-ant-good", http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler))).check("claude-haiku-5-5"))
    assert ok["ok"] and seen == [("GET", "/v1/models/claude-haiku-5-5")]  # /v1/messages çağrılmadı
    bad = asyncio.run(AnthropicProvider("sk-ant-bad", http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler))).check("claude-haiku-5-5"))
    assert not bad["ok"] and "401" in bad["message"]
    none = asyncio.run(AnthropicProvider("").check("claude-haiku-5-5"))
    assert none == {"ok": False, "configured": False, "message": "ANTHROPIC_API_KEY ayarlı değil"}


@pytest.mark.no_llm
def test_check_providers_endpoint(client):
    r = client.post("/api/system/check-providers", headers=H).json()
    assert r["results"] and r["usd_try_rate_set"] is True


# ---------------- canlı test düzeneği ----------------
@pytest.mark.fake_llm
def test_live_harness_with_fake_is_not_reported_as_real(tmp_path):
    from app.livetest import CODEWORD, TASK_TITLE, run_live
    from app.llm.router import LLMRouter
    s = make_settings(tmp_path)
    db = Database(s.db_path); db.init()
    p = FakeProvider(replies=[
        "BULUT hazır",
        {"tools": [("search_memory", {"query": "kod kelime"})]}, CODEWORD,
        {"tools": [("create_task", {"title": TASK_TITLE, "kind": "manual", "priority": 3, "project_slug": "yan-daire"})]}, "Eklendi.",
    ])
    rep = asyncio.run(run_live(s, db, LLMRouter(db, s, {"anthropic": p})))
    assert rep["ran"] and rep["real_api"] is False  # sahte sağlayıcı gerçek API sayılmaz
    assert [r["status"] for r in rep["results"]] == ["PASS", "PASS", "PASS"], rep["results"]
    assert (tmp_path / "live_tests" / rep["report_file"]).exists()
    assert db.query("SELECT * FROM tasks") == [] and db.query("SELECT * FROM memories") == []  # ana veri kirlenmedi
    assert db.one("SELECT COUNT(*) AS n FROM llm_calls")["n"] == 5  # maliyet ana bütçeye yazıldı
    assert "SAHTE" in db.one("SELECT summary FROM activity WHERE kind='live_test'")["summary"]


@pytest.mark.fake_llm
def test_live_harness_detects_model_not_using_tool(tmp_path):
    from app.livetest import CODEWORD, run_live
    from app.llm.router import LLMRouter
    s = make_settings(tmp_path)
    db = Database(s.db_path); db.init()
    p = FakeProvider(replies=[CODEWORD])  # araç kullanmadan "tahmin"
    rep = asyncio.run(run_live(s, db, LLMRouter(db, s, {"anthropic": p}), scenarios=("memory_search",)))
    assert rep["results"][0]["status"] == "FAIL" and "araçlar=hiç" in rep["results"][0]["detail"]


@pytest.mark.no_llm
def test_live_without_key_does_not_run(tmp_path):
    from app.livetest import run_live
    from app.llm.providers import AnthropicProvider
    from app.llm.router import LLMRouter
    s = make_settings(tmp_path)
    db = Database(s.db_path); db.init()
    rep = asyncio.run(run_live(s, db, LLMRouter(db, s, {"anthropic": AnthropicProvider("")})))
    assert rep["ran"] is False and rep["real_api"] is False and "ÇALIŞTIRILMADI" in rep["reason"]
    assert rep["results"] == []


@pytest.mark.no_llm
def test_live_endpoint_requires_explicit_confirmation(client):
    assert client.post("/api/system/live-test", json={"confirm": "evet"}, headers=H).status_code == 400
    assert client.fake.calls == []


@pytest.mark.fake_llm
def test_live_harness_respects_main_budget(tmp_path):
    from app.db import now_iso
    from app.livetest import run_live
    from app.llm.router import LLMRouter
    s = make_settings(tmp_path, monthly_budget_try=10.0)
    db = Database(s.db_path); db.init()
    with db.tx() as t:  # ana DB'de bu ay 9.99 TL harcanmış (kur 40)
        t.execute("INSERT INTO llm_calls(provider,model,purpose,cost_usd,ok,created_at) VALUES ('anthropic','m','x',?,1,?)",
                  (9.99 / 40, now_iso()))
    p = FakeProvider()
    rep = asyncio.run(run_live(s, db, LLMRouter(db, s, {"anthropic": p}), scenarios=("chat",)))
    assert rep["results"][0]["status"] == "ERROR" and "bütçe" in rep["results"][0]["detail"].lower()
    assert p.calls == []
