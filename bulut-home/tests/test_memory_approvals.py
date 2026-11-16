import pytest

from app import approvals, memory
from app.db import Database
from conftest import H

import pytest as _pt

pytestmark = _pt.mark.no_llm


def test_memory_crud_and_search(client):
    r = client.post("/api/memories", json={"content": "Kullanıcı After Effects ile motion design yapıyor", "kind": "fact"}, headers=H)
    mid = r.json()["id"]
    assert client.get("/api/memories", params={"q": "motion"}).json()[0]["id"] == mid
    # Türkçe ek toleransı: "Effects'te" → önek
    assert client.get("/api/memories", params={"q": "effects'te"}).json()
    client.patch(f"/api/memories/{mid}", json={"content": "Kullanıcı Premiere ile kurgu yapıyor"}, headers=H)
    assert client.get("/api/memories", params={"q": "motion"}).json() == []
    assert client.get("/api/memories", params={"q": "premiere"}).json()[0]["id"] == mid
    assert client.delete(f"/api/memories/{mid}", headers=H).status_code == 200
    assert client.get("/api/memories").json() == []


def test_memory_duplicate_merges(tmp_path):
    db = Database(tmp_path / "x.db"); db.init()
    a = memory.add(db, "Aynı bilgi")
    b = memory.add(db, "aynı bilgi")
    assert a == b


def test_project_delete_requires_approval(client):
    pid = client.post("/api/projects", json={"name": "Deneme", "slug": "deneme"}, headers=H).json()["id"]
    r = client.delete(f"/api/projects/{pid}", headers=H)
    assert r.status_code == 202 and r.json()["approval_required"]
    # henüz silinmedi
    assert any(p["id"] == pid for p in client.get("/api/projects").json())
    aid = r.json()["approval_id"]
    res = client.post(f"/api/approvals/{aid}/approve", headers=H).json()
    assert res["status"] == "executed"
    assert not any(p["id"] == pid for p in client.get("/api/projects").json())
    # ikinci kez onaylanamaz / yürütülemez
    assert client.post(f"/api/approvals/{aid}/approve", headers=H).status_code == 409


def test_rejected_approval_does_nothing(client):
    pid = client.post("/api/projects", json={"name": "Kalsın", "slug": "kalsin"}, headers=H).json()["id"]
    aid = client.delete(f"/api/projects/{pid}", headers=H).json()["approval_id"]
    assert client.post(f"/api/approvals/{aid}/reject", headers=H).json()["status"] == "rejected"
    assert any(p["id"] == pid for p in client.get("/api/projects").json())


def test_execute_without_approval_is_impossible(tmp_path):
    db = Database(tmp_path / "x.db"); db.init()
    aid = approvals.request(db, "delete_data", "test", {"project_id": 1}, executor_name="delete_project")
    with pytest.raises(PermissionError):
        approvals.execute(db, aid)
    assert db.one("SELECT COUNT(*) AS n FROM projects WHERE id=1")["n"] == 1


@_pt.mark.fake_llm
def test_system_and_reports(client):
    client.post("/api/chat", json={"message": "selam"}, headers=H)
    s = client.get("/api/system").json()
    assert s["budget"]["calls_this_month"] == 1 and s["budget"]["blocked"] is False
    rep = client.get("/api/reports/daily").json()
    assert rep["cost_by_day"][0]["calls"] == 1
    assert client.post("/api/system/backup", headers=H).json()["ok"]
    assert client.get("/api/system").json()["backups"]
    assert client.get("/api/activity").json()
