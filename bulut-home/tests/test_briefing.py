"""Günlük brifing: veri toplama gerçek DB üzerinde; model metni FakeProvider (fake_llm)."""
import asyncio
from datetime import datetime, timezone

import pytest

from app import briefing, tasks
from app.db import Database
from app.llm.router import LLMRouter
from conftest import H, FakeProvider, make_settings


def _db(tmp_path):
    db = Database(tmp_path / "b.db"); db.init()
    return db


@pytest.mark.no_llm
def test_collect_and_render_from_real_records(tmp_path):
    db = _db(tmp_path)
    a = tasks.create(db, "Logo tasarımı bitir", project_id=1)
    tasks.set_status(db, a["id"], "done")
    tasks.create(db, "Fiverr profilini güncelle", priority=1)
    d = briefing.collect(db)
    assert [t["title"] for t in d["tasks_done"]] == ["Logo tasarımı bitir"]
    assert d["tasks_open"][0]["title"] == "Fiverr profilini güncelle"
    text = briefing.render(d, 40.0)
    assert "Logo tasarımı bitir" in text and "P1" in text and "TL" in text


@pytest.mark.no_llm
def test_generate_without_model_falls_back(tmp_path):
    db = _db(tmp_path)
    s = make_settings(tmp_path)
    router = LLMRouter(db, s, {})
    b = asyncio.run(briefing.generate(db, router, "Europe/Istanbul", None))
    assert b["source"] == "deterministic" and "yapılandırılmamış" in b["note"]
    assert "Açık görev yok" in b["content"]


@pytest.mark.fake_llm
def test_generate_with_model_and_upsert(tmp_path):
    db = _db(tmp_path)
    s = make_settings(tmp_path)
    p = FakeProvider(replies=["Dün 0 iş bitti.", "Güncel brifing."])
    router = LLMRouter(db, s, {"anthropic": p})
    b1 = asyncio.run(briefing.generate(db, router, "Europe/Istanbul", 40.0, day="2026-11-16"))
    assert b1["source"] == "llm" and b1["content"] == "Dün 0 iş bitti."
    assert '"tasks_done": []' in p.calls[0]["messages"][0]["content"]  # model yalnızca gerçek JSON görür
    asyncio.run(briefing.generate(db, router, "Europe/Istanbul", 40.0, day="2026-11-16"))
    rows = db.query("SELECT * FROM briefings")
    assert len(rows) == 1 and rows[0]["content"] == "Güncel brifing."


@pytest.mark.no_llm
def test_schedule_once_per_day_after_time(tmp_path):
    db = _db(tmp_path)
    before = datetime(2026, 11, 16, 5, 0, tzinfo=timezone.utc)   # 08:00 İstanbul
    after = datetime(2026, 11, 16, 6, 0, tzinfo=timezone.utc)    # 09:00 İstanbul
    assert briefing.maybe_schedule(db, "08:30", "Europe/Istanbul", before) is None
    t = briefing.maybe_schedule(db, "08:30", "Europe/Istanbul", after)
    assert t and t["kind"] == "brief" and t["dedupe_key"] == "brief:2026-11-16"
    assert briefing.maybe_schedule(db, "08:30", "Europe/Istanbul", after) is None
    tasks.set_status(db, t["id"], "cancelled")
    assert briefing.maybe_schedule(db, "08:30", "Europe/Istanbul", after) is None  # günde bir kez
    assert briefing.maybe_schedule(db, "", "Europe/Istanbul", after) is None       # kapalı


@pytest.mark.fake_llm
def test_brief_task_runs_via_worker(tmp_path):
    db = _db(tmp_path)
    s = make_settings(tmp_path)
    router = LLMRouter(db, s, {"anthropic": FakeProvider(replies=["Sabah brifingi."])})
    briefing.maybe_schedule(db, "00:00", "Europe/Istanbul")
    out = asyncio.run(tasks.TaskWorker(db, router).run_one())
    assert out["status"] == "done" and out["output"].startswith("Sabah brifingi.")
    assert db.one("SELECT source FROM briefings")["source"] == "llm"


@pytest.mark.fake_llm
def test_briefing_api(client):
    client.fake.replies = ["API brifingi."]
    b = client.post("/api/briefings/generate", headers=H).json()
    assert b["content"] == "API brifingi."
    assert client.get("/api/briefings").json()[0]["day"] == b["day"]
    s = client.get("/api/system").json()
    assert s["web"]["search_backend"] is None and s["briefing"]["time"] == "08:30"


@pytest.mark.no_llm
def test_brief_tasks_not_listed_as_work(tmp_path):
    db = _db(tmp_path)
    t = briefing.maybe_schedule(db, "00:00", "Europe/Istanbul")
    tasks.set_status(db, t["id"], "done")
    d = briefing.collect(db)
    assert d["tasks_done"] == [] and d["tasks_open"] == []
