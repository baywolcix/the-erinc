"""Genel zamanlanmış görevler: ayrıştırma, saat dilimi, tek çalışma garantisi, yeniden başlatma, kaçırılan çalışmalar."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app import schedules, tasks
from app.db import Database
from conftest import H

TZ = "Europe/Istanbul"
pytestmark = pytest.mark.no_llm


def _db(tmp_path):
    db = Database(tmp_path / "s.db"); db.init()
    return db


def U(*a):
    return datetime(*a, tzinfo=timezone.utc)


@pytest.mark.parametrize("spec", ["daily 25:00", "weekly xyz 09:00", "monthly 31 10:00", "every 5m", "every 8d", "her gün", ""])
def test_invalid_specs(spec):
    with pytest.raises(ValueError):
        schedules.parse(spec)


def test_next_after_timezone_and_kinds():
    # 2026-11-16 Pazartesi; İstanbul UTC+3
    assert schedules.next_after("daily 08:30", U(2026, 11, 16, 4, 0), TZ) == U(2026, 11, 16, 5, 30)
    assert schedules.next_after("daily 08:30", U(2026, 11, 16, 5, 30), TZ) == U(2026, 11, 17, 5, 30)  # kesinlikle sonrası
    assert schedules.next_after("weekly per,cum 09:00", U(2026, 11, 16, 12, 0), TZ) == U(2026, 11, 19, 6, 0)  # Perşembe
    assert schedules.next_after("monthly 1 10:00", U(2026, 11, 16, 12, 0), TZ) == U(2026, 12, 1, 7, 0)
    assert schedules.next_after("every 6h", U(2026, 11, 16, 12, 0), TZ) == U(2026, 11, 16, 18, 0)
    assert schedules.describe("weekly mon,thu 09:00") == "Her Pzt, Per 09:00"


def test_tick_creates_once_per_slot(tmp_path):
    db = _db(tmp_path)
    s = schedules.create(db, "Sabah", "daily 08:30", "Bionluk ilanlarını kontrol et", tz=TZ)
    slot = datetime.fromisoformat(s["next_run_at"])
    assert schedules.tick(db, TZ, slot - timedelta(seconds=1)) == []  # vakti gelmedi
    out = schedules.tick(db, TZ, slot)
    assert len(out) == 1 and out[0]["status"] == "created"
    assert schedules.tick(db, TZ, slot) == []  # aynı anda ikinci tick → yeni görev yok
    assert tasks.list_tasks(db)[0]["title"] == "Bionluk ilanlarını kontrol et"
    s2 = schedules.get(db, s["id"])
    assert datetime.fromisoformat(s2["next_run_at"]) == slot + timedelta(days=1)


def test_same_slot_cannot_run_twice_even_if_next_run_reset(tmp_path):
    db = _db(tmp_path)
    s = schedules.create(db, "X", "daily 08:30", "iş", tz=TZ)
    slot = s["next_run_at"]
    schedules.tick(db, TZ, datetime.fromisoformat(slot))
    tasks.set_status(db, tasks.list_tasks(db)[0]["id"], "done")
    with db.tx() as t:  # çökme sonrası next_run_at geri kalmış gibi
        t.execute("UPDATE schedules SET next_run_at=? WHERE id=?", (slot, s["id"]))
    assert schedules.tick(db, TZ, datetime.fromisoformat(slot) + timedelta(minutes=1)) == []
    assert len(tasks.list_tasks(db)) == 1


def test_survives_restart(tmp_path):
    db = _db(tmp_path)
    s = schedules.create(db, "Haftalık", "weekly mon 10:00", "Haftalık plan", tz=TZ)
    db2 = Database(db.path); db2.init()  # yeniden başlatma
    assert schedules.get(db2, s["id"])["next_run_at"] == s["next_run_at"]
    assert schedules.tick(db2, TZ, datetime.fromisoformat(s["next_run_at"]))[0]["status"] == "created"


def test_missed_runs_catch_up_once(tmp_path):
    db = _db(tmp_path)
    s = schedules.create(db, "Saatlik", "every 1h", "kontrol", tz=TZ)
    later = datetime.fromisoformat(s["next_run_at"]) + timedelta(hours=10)  # 10 saat kapalı kaldı
    out = schedules.tick(db, TZ, later)
    assert len(out) == 1 and len(tasks.list_tasks(db)) == 1
    assert datetime.fromisoformat(schedules.get(db, s["id"])["next_run_at"]) == later + timedelta(hours=1)


def test_skips_when_previous_task_still_active(tmp_path):
    db = _db(tmp_path)
    s = schedules.create(db, "Sık", "every 15m", "uzun iş", tz=TZ)
    t1 = datetime.fromisoformat(s["next_run_at"])
    schedules.tick(db, TZ, t1)
    out = schedules.tick(db, TZ, t1 + timedelta(minutes=15))
    assert out[0]["status"] == "skipped_active" and len(tasks.list_tasks(db)) == 1
    tasks.set_status(db, tasks.list_tasks(db)[0]["id"], "done")
    assert schedules.tick(db, TZ, t1 + timedelta(minutes=30))[0]["status"] == "created"


def test_disabled_does_not_run(tmp_path):
    db = _db(tmp_path)
    s = schedules.create(db, "Kapalı", "every 15m", "x", enabled=False, tz=TZ)
    assert schedules.tick(db, TZ, datetime.fromisoformat(s["next_run_at"]) + timedelta(days=1)) == []


@pytest.mark.fake_llm
def test_model_created_paid_schedule_needs_approval(client):
    client.fake.replies = [{"tools": [("create_schedule", {"name": "İlan taraması", "spec": "weekly mon 09:00",
                                                            "title": "Fiverr motion design ilanlarını özetle", "kind": "llm"})]}, "Onaya gönderdim."]
    client.post("/api/chat", json={"message": "Her pazartesi ilanları tara"}, headers=H)
    s = client.get("/api/schedules").json()[0]
    assert s["enabled"] == 0 and s["created_by"].startswith("model:")
    ap = client.get("/api/approvals?status=pending").json()[0]
    assert ap["action"] == "spend_money"
    client.post(f"/api/approvals/{ap['id']}/approve", headers=H)
    assert client.get("/api/schedules").json()[0]["enabled"] == 1


@pytest.mark.fake_llm
def test_model_created_manual_schedule_enabled(client):
    client.fake.replies = [{"tools": [("create_schedule", {"name": "Hatırlatma", "spec": "daily 20:00",
                                                            "title": "Günlük render kuyruğunu kontrol et", "kind": "manual"})]}, "Tamam."]
    client.post("/api/chat", json={"message": "Her akşam hatırlat"}, headers=H)
    assert client.get("/api/schedules").json()[0]["enabled"] == 1
    assert client.get("/api/approvals?status=pending").json() == []


def test_schedule_api(client):
    r = client.post("/api/schedules/preview", json={"spec": "weekly pzt 09:00"}, headers=H).json()
    assert r["description"] == "Her Pzt 09:00" and len(r["next"]) == 3
    assert client.post("/api/schedules/preview", json={"spec": "her pazartesi"}, headers=H).status_code == 400
    s = client.post("/api/schedules", json={"name": "Yedek", "spec": "daily 03:00", "title": "Yedekleri kontrol et"}, headers=H).json()
    assert s["enabled"] == 1 and s["description_human"] == "Her gün 03:00"
    assert client.patch(f"/api/schedules/{s['id']}", json={"enabled": False}, headers=H).json()["enabled"] == 0
    assert client.patch(f"/api/schedules/{s['id']}", json={"spec": "bozuk"}, headers=H).status_code == 400
    assert client.delete(f"/api/schedules/{s['id']}", headers=H).json()["ok"]
    assert client.get("/api/schedules").json() == []
