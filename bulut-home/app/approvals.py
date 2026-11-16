"""Onay mekanizması — uygulama kodunda zorunlu.

Kritik işlemler doğrudan çalıştırılamaz. Önce `request()` ile onay kaydı açılır;
yalnızca sahibi /api/approvals/{id}/approve ile onaylarsa `execute()` işlemi çalıştırır.
Her onay en fazla bir kez yürütülür (atomik durum geçişi).
"""
from __future__ import annotations

import json
from typing import Callable

from .db import Database, now_iso, log_activity

CRITICAL_ACTIONS = {
    "spend_money": "Para harcama",
    "delete_data": "Dosya veya önemli veri silme",
    "account_change": "Kritik hesap ayarı değişikliği",
    "live_change": "Canlı sistemde riskli değişiklik",
    "external_irreversible": "Harici hesapta geri alınamaz işlem",
}

# action_type -> yürütücü(db, payload) ; yalnızca onaylı kayıtla çağrılır
_EXECUTORS: dict[str, Callable[[Database, dict], str]] = {}


class ApprovalRequired(Exception):
    def __init__(self, approval_id: int):
        super().__init__(f"Onay gerekiyor (#{approval_id})")
        self.approval_id = approval_id


def executor(name: str):
    def deco(fn):
        _EXECUTORS[name] = fn
        return fn
    return deco


def request(db: Database, action: str, summary: str, payload: dict | None = None,
            task_id: int | None = None, executor_name: str | None = None) -> int:
    if action not in CRITICAL_ACTIONS:
        raise ValueError(f"Bilinmeyen kritik işlem türü: {action}")
    data = dict(payload or {})
    if executor_name:
        if executor_name not in _EXECUTORS:
            raise ValueError(f"Bilinmeyen yürütücü: {executor_name}")
        data["_executor"] = executor_name
    with db.tx() as t:
        cur = t.execute(
            "INSERT INTO approvals(action,summary,payload,task_id,status,created_at) VALUES (?,?,?,?, 'pending', ?)",
            (action, summary, json.dumps(data, ensure_ascii=False), task_id, now_iso()),
        )
        aid = cur.lastrowid
    log_activity(db, "approval_requested", f"Onay bekleniyor: {summary}", ref=f"approval:{aid}", level="warn")
    from .notify import notify
    notify(db, "approval_requested", "Onayın bekleniyor", f"{CRITICAL_ACTIONS[action]}: {summary}", "critical",
           f"approval:{aid}", dedupe_key=f"notify:approval:{aid}")
    return aid


def decide(db: Database, approval_id: int, approve: bool, by: str) -> dict:
    with db.tx() as t:
        row = t.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
        if not row:
            raise KeyError("Onay kaydı bulunamadı")
        if row["status"] != "pending":
            raise ValueError(f"Bu onay zaten '{row['status']}' durumunda")
        status = "approved" if approve else "rejected"
        t.execute("UPDATE approvals SET status=?, decided_at=?, decided_by=? WHERE id=?",
                  (status, now_iso(), by, approval_id))
        if row["task_id"]:
            if approve:
                t.execute("UPDATE tasks SET status='pending', updated_at=? WHERE id=? AND status='waiting_approval'",
                          (now_iso(), row["task_id"]))
            else:
                t.execute("UPDATE tasks SET status='cancelled', last_error='Kullanıcı onaylamadı', updated_at=?, "
                          "finished_at=? WHERE id=? AND status='waiting_approval'", (now_iso(), now_iso(), row["task_id"]))
    log_activity(db, f"approval_{status}", f"{'Onaylandı' if approve else 'Reddedildi'}: {row['summary']}",
                 ref=f"approval:{approval_id}")
    result = {"id": approval_id, "status": status}
    if approve:
        payload = json.loads(row["payload"] or "{}")
        if payload.get("_executor"):
            result["result"] = execute(db, approval_id)
            result["status"] = "executed"
    return result


def is_approved(db: Database, approval_id: int | None) -> bool:
    if not approval_id:
        return False
    row = db.one("SELECT status FROM approvals WHERE id=?", (approval_id,))
    return bool(row) and row["status"] in ("approved", "executed")


def execute(db: Database, approval_id: int) -> str:
    """Onaylı işlemi tam olarak bir kez çalıştır."""
    with db.tx() as t:
        row = t.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
        if not row or row["status"] != "approved":
            raise PermissionError("İşlem onaylı değil; yürütülemez.")
        t.execute("UPDATE approvals SET status='executed', executed_at=? WHERE id=?", (now_iso(), approval_id))
    payload = json.loads(row["payload"] or "{}")
    fn = _EXECUTORS.get(payload.pop("_executor", ""))
    if fn is None:
        return "Yürütücü yok; onay kaydedildi."
    try:
        out = fn(db, payload)
    except Exception as e:  # noqa: BLE001 — onay tüketildi; hata gizlenmemeli
        msg = f"Yürütme hatası: {type(e).__name__}: {e}"
        log_activity(db, "approval_failed", f"Onaylı işlem başarısız: {row['summary']}", detail=msg,
                     ref=f"approval:{approval_id}", level="error")
        return msg
    log_activity(db, "approval_executed", f"Yürütüldü: {row['summary']}", detail=out, ref=f"approval:{approval_id}")
    return out


# ---------- kayıtlı kritik yürütücüler ----------

@executor("delete_project")
def _delete_project(db: Database, payload: dict) -> str:
    pid = int(payload["project_id"])
    with db.tx() as t:
        n = t.execute("DELETE FROM projects WHERE id=?", (pid,)).rowcount
    return f"Proje #{pid} silindi" if n else f"Proje #{pid} zaten yoktu"


@executor("clear_memories")
def _clear_memories(db: Database, payload: dict) -> str:
    with db.tx() as t:
        n = t.execute("DELETE FROM memories WHERE pinned=0" if payload.get("keep_pinned", True) else "DELETE FROM memories").rowcount
    return f"{n} hafıza kaydı silindi"
