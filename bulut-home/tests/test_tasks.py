import asyncio

from app import approvals, tasks
from app.db import Database
from app.llm.router import LLMRouter
from conftest import H, FakeProvider, make_settings


def _env(tmp_path, provider=None, **over):
    s = make_settings(tmp_path, **over)
    db = Database(s.db_path)
    db.init()
    router = LLMRouter(db, s, {"anthropic": provider or FakeProvider()})
    return db, tasks.TaskWorker(db, router)


def test_dedupe(tmp_path):
    db, _ = _env(tmp_path)
    a = tasks.create(db, "X", dedupe_key="k")
    b = tasks.create(db, "X tekrar", dedupe_key="k")
    assert a["id"] == b["id"] and b["deduplicated"]
    tasks.set_status(db, a["id"], "done")
    c = tasks.create(db, "X yeni", dedupe_key="k")  # eskisi bitti → yeni açılabilir
    assert c["id"] != a["id"]


def test_claim_is_exclusive(tmp_path):
    db, w = _env(tmp_path)
    tasks.create(db, "llm işi", kind="llm")
    first = w.claim_next()
    assert first and first["status"] == "running"
    assert w.claim_next() is None


def test_manual_tasks_not_executed(tmp_path):
    db, w = _env(tmp_path)
    tasks.create(db, "elle iş", kind="manual")
    assert asyncio.run(w.run_one()) is None


def test_llm_task_runs(tmp_path):
    db, w = _env(tmp_path, FakeProvider(replies=["teklif taslağı"]))
    t = tasks.create(db, "Teklif yaz", kind="llm")
    out = asyncio.run(w.run_one())
    assert out["id"] == t["id"] and out["status"] == "done" and out["output"] == "teklif taslağı"


def test_retry_then_fail(tmp_path):
    db, w = _env(tmp_path, FakeProvider(fail_times=99))
    t = tasks.create(db, "kırılgan", kind="llm", max_attempts=2)
    r1 = asyncio.run(w.run_one())
    assert r1["status"] == "pending" and r1["attempts"] == 1 and r1["next_run_at"]
    with db.tx() as c:
        c.execute("UPDATE tasks SET next_run_at=NULL WHERE id=?", (t["id"],))
    r2 = asyncio.run(w.run_one())
    assert r2["status"] == "failed" and "simüle" in r2["last_error"]
    assert db.one("SELECT 1 AS x FROM activity WHERE kind='task_failed'")


def test_restart_recovers_running(tmp_path):
    db, w = _env(tmp_path)
    tasks.create(db, "yarım", kind="llm")
    w.claim_next()
    Database(db.path).init()  # yeniden başlatma
    assert db.one("SELECT status FROM tasks")["status"] == "pending"


def test_plan_creates_subtasks(tmp_path):
    reply = 'İşte plan: [{"title": "Portföy güncelle", "priority": 1, "kind": "manual"}, {"title": "Bionluk ilanı yaz", "priority": 2, "kind": "llm"}]'
    db, w = _env(tmp_path, FakeProvider(replies=[reply]))
    t = tasks.create(db, "Bu ay 5 yeni müşteri", kind="plan")
    out = asyncio.run(w.run_one())
    assert out["status"] == "done"
    kids = db.query("SELECT title, kind, parent_id, origin FROM tasks WHERE parent_id=? ORDER BY id", (t["id"],))
    assert [k["title"] for k in kids] == ["Portföy güncelle", "Bionluk ilanı yaz"]
    assert kids[1]["kind"] == "llm" and kids[0]["origin"] == "goal"


def test_expensive_task_needs_approval(tmp_path):
    # Çok pahalı fiyat → tahmin eşiği aşar → onaya düşer, model çağrılmaz
    from app.llm.pricing import Price
    p = FakeProvider(price=Price(100.0, 500.0))
    db, w = _env(tmp_path, p, monthly_budget_try=100000)
    t = tasks.create(db, "pahalı", kind="llm")
    out = asyncio.run(w.run_one())
    assert out["status"] == "waiting_approval" and p.calls == []
    ap = db.one("SELECT * FROM approvals WHERE task_id=?", (t["id"],))
    assert ap["action"] == "spend_money"
    approvals.decide(db, ap["id"], True, "umut")
    out2 = asyncio.run(w.run_one())
    assert out2["status"] == "done" and len(p.calls) == 1


def test_task_api(client):
    r = client.post("/api/tasks", json={"title": "Kapak tasarla", "project_id": 1, "priority": 2}, headers=H)
    assert r.status_code == 200
    tid = r.json()["id"]
    lst = client.get("/api/tasks").json()
    assert lst["counts"]["pending"] == 1
    assert client.post(f"/api/tasks/{tid}/status", json={"status": "done"}, headers=H).json()["status"] == "done"
    assert client.post(f"/api/tasks/{tid}/status", json={"status": "running"}, headers=H).status_code == 400
    assert client.post("/api/tasks", json={"title": "x", "kind": "hack"}, headers=H).status_code == 400
