"""Bildirim sistemi: olay kancaları, kuyruk, yeniden deneme, sessiz saat, ntfy/Telegram biçimi (sahte HTTP, ağa çıkmaz)."""
import asyncio
import json
from datetime import datetime, timezone

import httpx2
import pytest

from app import approvals, notify, tasks
from app.db import Database
from app.llm.router import LLMRouter
from conftest import H, FakeProvider, make_settings

pytestmark = pytest.mark.no_llm


class Recorder:
    def __init__(self, fail=0, status=200):
        self.requests, self.fail, self.status = [], fail, status

    def __call__(self, req):
        self.requests.append({"url": str(req.url), "json": json.loads(req.content), "auth": req.headers.get("authorization")})
        if self.fail > 0:
            self.fail -= 1
            return httpx2.Response(500, text="hata")
        return httpx2.Response(self.status, json={"ok": True})


def _db(tmp_path):
    db = Database(tmp_path / "n.db"); db.init()
    return db


def _cfg(rec, **kw):
    base = dict(ntfy_topic="bulut-gizli-konu-123", ntfy_token="tk_" + "x" * 25, telegram_bot_token="123456789:" + "A" * 35,
                telegram_chat_id="987654", transport=httpx2.MockTransport(rec), public_url="https://bulut.example.ts.net")
    base.update(kw)
    return notify.NotifyConfig(**base)


def test_in_app_only_without_channels(tmp_path):
    db = _db(tmp_path)
    nid = notify.notify(db, "x", "Başlık", "gövde", "critical")
    assert nid and db.query("SELECT * FROM notification_deliveries") == []
    assert notify.list_notifications(db)["unread"] == 1


def test_ntfy_and_telegram_payloads(tmp_path):
    rec = Recorder()
    notify.configure(_cfg(rec))
    db = _db(tmp_path)
    notify.notify(db, "task_failed", "Görev başarısız: Kapak", "Hata ayrıntısı", "critical", "task:5")
    stats = asyncio.run(notify.deliver_pending(db))
    assert stats["sent"] == 2
    ntfy = next(r for r in rec.requests if "ntfy" in r["url"])
    assert ntfy["json"]["topic"] == "bulut-gizli-konu-123" and ntfy["json"]["title"] == "Görev başarısız: Kapak"
    assert ntfy["json"]["priority"] == 5 and ntfy["json"]["click"] == "https://bulut.example.ts.net"
    assert ntfy["auth"] == "Bearer " + "tk_" + "x" * 25
    tg = next(r for r in rec.requests if "telegram" in r["url"])
    assert tg["json"]["chat_id"] == "987654" and "Görev başarısız: Kapak" in tg["json"]["text"]


def test_min_level_filters_mobile_but_keeps_in_app(tmp_path):
    rec = Recorder()
    notify.configure(_cfg(rec, min_level="important"))
    db = _db(tmp_path)
    notify.notify(db, "task_done", "Küçük iş bitti", level="info")
    assert db.query("SELECT * FROM notification_deliveries") == []
    assert notify.list_notifications(db)["unread"] == 1


def test_retry_backoff_then_failed(tmp_path):
    rec = Recorder(fail=99)
    notify.configure(_cfg(rec, telegram_bot_token=""))
    db = _db(tmp_path)
    notify.notify(db, "x", "t", level="critical")
    from datetime import timedelta
    t0 = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=5)
    s1 = asyncio.run(notify.deliver_pending(db, now=t0))
    assert s1["retry"] == 1
    d = db.one("SELECT * FROM notification_deliveries")
    assert d["status"] == "pending" and d["attempts"] == 1
    assert d["next_attempt_at"] == (t0 + timedelta(seconds=60)).isoformat(timespec="seconds")
    assert asyncio.run(notify.deliver_pending(db, now=t0))["retry"] == 0  # vakti gelmedi
    for minutes in (2, 10, 60):
        asyncio.run(notify.deliver_pending(db, now=t0 + timedelta(minutes=minutes)))
    d = db.one("SELECT * FROM notification_deliveries")
    assert d["status"] == "failed" and d["attempts"] == notify.MAX_ATTEMPTS and "HTTP 500" in d["last_error"]


def test_token_never_stored_in_errors(tmp_path):
    token = "123456789:" + "B" * 35

    def boom(req):
        raise httpx2.ConnectError(f"connect failed for {req.url}")
    notify.configure(_cfg(None, ntfy_topic="", telegram_bot_token=token, transport=httpx2.MockTransport(boom)))
    from app.redact import register
    register(token)
    db = _db(tmp_path)
    notify.notify(db, "x", "t", level="critical")
    asyncio.run(notify.deliver_pending(db))
    assert token not in db.one("SELECT last_error FROM notification_deliveries")["last_error"]


def test_quiet_hours_defer_non_critical(tmp_path):
    rec = Recorder()
    notify.configure(_cfg(rec, telegram_bot_token="", quiet="23:00-08:00", min_level="info"))
    db = _db(tmp_path)
    notify.notify(db, "a", "önemli", level="important")
    notify.notify(db, "b", "kritik", level="critical")
    from datetime import timedelta
    base = datetime.now(timezone.utc) + timedelta(days=1)
    night = base.replace(hour=22, minute=0, second=0, microsecond=0)  # 01:00 İstanbul (ertesi gün)
    s = asyncio.run(notify.deliver_pending(db, now=night))
    assert s == {"sent": 1, "failed": 0, "deferred": 1, "retry": 0}
    assert rec.requests[0]["json"]["title"] == "kritik"
    d = db.one("SELECT next_attempt_at FROM notification_deliveries WHERE status='pending'")
    assert d["next_attempt_at"] == (night + timedelta(hours=7)).isoformat(timespec="seconds")  # 08:00 İstanbul


def test_details_off_hides_body(tmp_path):
    rec = Recorder()
    notify.configure(_cfg(rec, telegram_bot_token="", details=False))
    db = _db(tmp_path)
    notify.notify(db, "x", "Görev tamamlandı", "gizli müşteri adı", "critical", "task:9")
    asyncio.run(notify.deliver_pending(db))
    assert "gizli" not in rec.requests[0]["json"]["message"] and "task:9" in rec.requests[0]["json"]["message"]


def test_dedupe(tmp_path):
    db = _db(tmp_path)
    assert notify.notify(db, "x", "a", dedupe_key="k1")
    assert notify.notify(db, "x", "a", dedupe_key="k1") is None
    assert db.one("SELECT COUNT(*) AS n FROM notifications")["n"] == 1


def test_pending_survives_restart(tmp_path):
    rec = Recorder()
    notify.configure(_cfg(rec, telegram_bot_token=""))
    db = _db(tmp_path)
    notify.notify(db, "x", "kalıcı", level="critical")
    db2 = Database(db.path); db2.init()  # yeniden başlatma
    assert asyncio.run(notify.deliver_pending(db2))["sent"] == 1


def test_event_hooks(tmp_path):
    db = _db(tmp_path)
    s = make_settings(tmp_path)
    w = tasks.TaskWorker(db, LLMRouter(db, s, {"anthropic": FakeProvider(replies=["sonuç"])}))
    tasks.create(db, "Rapor yaz", kind="llm")
    asyncio.run(w.run_one())
    w2 = tasks.TaskWorker(db, LLMRouter(db, s, {"anthropic": FakeProvider(fail_times=9)}))
    tasks.create(db, "Kırılgan", kind="llm", max_attempts=1)
    asyncio.run(w2.run_one())
    approvals.request(db, "delete_data", "Projeyi sil", {})
    events = [r["event"] for r in db.query("SELECT event FROM notifications ORDER BY id")]
    assert events == ["task_done", "task_failed", "approval_requested"]
    levels = {r["event"]: r["level"] for r in db.query("SELECT event, level FROM notifications")}
    assert levels == {"task_done": "important", "task_failed": "critical", "approval_requested": "critical"}


def test_budget_notifications_once_per_month(tmp_path):
    db = _db(tmp_path)
    notify.budget_check(db, 85, 100)
    notify.budget_check(db, 90, 100)
    notify.budget_check(db, 100, 100)
    notify.budget_check(db, 120, 100)
    assert [r["event"] for r in db.query("SELECT event FROM notifications ORDER BY id")] == ["budget_warning", "budget_blocked"]


@pytest.mark.fake_llm
def test_router_emits_budget_warning(tmp_path):
    s = make_settings(tmp_path, monthly_budget_try=0.095)  # 1 çağrı ≈0.08 TL → %84
    db = Database(s.db_path); db.init()
    asyncio.run(LLMRouter(db, s, {"anthropic": FakeProvider()}).complete(system="s", messages=[{"role": "user", "content": "x"}], max_tokens=10))
    assert db.one("SELECT event FROM notifications")["event"] == "budget_warning"


def test_notification_api(client):
    client.post("/api/projects", json={"name": "Sil", "slug": "sil"}, headers=H)
    pid = [p for p in client.get("/api/projects").json() if p["slug"] == "sil"][0]["id"]
    client.delete(f"/api/projects/{pid}", headers=H)
    n = client.get("/api/notifications").json()
    assert n["unread"] == 1 and n["items"][0]["event"] == "approval_requested" and n["channels"] == []
    assert client.post(f"/api/notifications/{n['items'][0]['id']}/read", headers=H).json()["marked"] == 1
    assert client.get("/api/notifications?unread=1").json()["items"] == []
    t = client.post("/api/notifications/test", headers=H).json()
    assert t["channels"] == [] and t["deliveries"] == []
