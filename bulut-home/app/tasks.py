"""Kalıcı görev kuyruğu ve tek işçili yürütücü.

- Görevler SQLite'ta; yeniden başlatmada kaybolmaz (çalışırken kalanlar 'pending'e döner).
- dedupe_key + kısmi benzersiz indeks: aynı aktif iş iki kez kuyruğa girmez.
- Atomik sahiplenme (UPDATE ... WHERE status='pending'): aynı iş iki kez çalışmaz.
- Sınırlı yeniden deneme + üstel geri çekilme; sonra 'failed' + aktivite kaydı.
- Tahmini maliyeti eşiği aşan görev önce onaya düşer.
"""
from __future__ import annotations

import asyncio
import json
import re
import socket
import sqlite3
from datetime import datetime, timedelta, timezone

from . import approvals
from .db import Database, now_iso, log_activity
from .llm.pricing import cost_usd
from .llm.router import BudgetError, LLMRouter, NoProviderError, ProvidersFailed

STATUSES = ("pending", "waiting_approval", "running", "done", "failed", "cancelled")
KINDS = {
    "manual": "Elle takip edilen iş (BULUT çalıştırmaz)",
    "llm": "BULUT'un model ile yürüttüğü metin işi (taslak, analiz, özet)",
    "plan": "Büyük hedefi alt görevlere ayırma",
}
APPROVAL_THRESHOLD_TRY = 5.0  # tek görev bu tutarı aşacaksa onay iste
WORKER_ID = f"{socket.gethostname()}-worker"


def create(db: Database, title: str, description: str = "", kind: str = "manual", project_id: int | None = None,
           priority: int = 3, origin: str = "board", parent_id: int | None = None,
           dedupe_key: str | None = None, max_attempts: int = 3) -> dict:
    title = title.strip()
    if not title:
        raise ValueError("Görev başlığı boş olamaz.")
    if kind not in KINDS:
        raise ValueError(f"Bilinmeyen görev türü: {kind}")
    priority = max(1, min(5, int(priority)))
    ts = now_iso()
    try:
        with db.tx() as t:
            cur = t.execute(
                "INSERT INTO tasks(title,description,kind,project_id,parent_id,priority,origin,status,dedupe_key,"
                "max_attempts,created_at,updated_at) VALUES (?,?,?,?,?,?,?, 'pending', ?,?,?,?)",
                (title, description, kind, project_id, parent_id, priority, origin, dedupe_key, max_attempts, ts, ts),
            )
            tid = cur.lastrowid
    except sqlite3.IntegrityError:
        existing = db.one("SELECT * FROM tasks WHERE dedupe_key=? AND status IN ('pending','waiting_approval','running')",
                          (dedupe_key,))
        if existing:
            existing["deduplicated"] = True
            return existing
        raise
    log_activity(db, "task_created", f"Görev oluşturuldu: {title}", ref=f"task:{tid}")
    return get(db, tid)


def get(db: Database, task_id: int) -> dict | None:
    return db.one("SELECT t.*, p.slug AS project_slug, p.name AS project_name FROM tasks t "
                  "LEFT JOIN projects p ON p.id=t.project_id WHERE t.id=?", (task_id,))


def list_tasks(db: Database, status: str | None = None, project_id: int | None = None, limit: int = 300) -> list[dict]:
    sql = ("SELECT t.*, p.slug AS project_slug, p.name AS project_name FROM tasks t "
           "LEFT JOIN projects p ON p.id=t.project_id WHERE 1=1")
    params: list = []
    if status:
        sql += " AND t.status=?"
        params.append(status)
    if project_id:
        sql += " AND t.project_id=?"
        params.append(project_id)
    sql += " ORDER BY CASE t.status WHEN 'running' THEN 0 WHEN 'waiting_approval' THEN 1 WHEN 'pending' THEN 2 " \
           "WHEN 'failed' THEN 3 ELSE 4 END, t.priority, t.id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def set_status(db: Database, task_id: int, status: str, note: str | None = None) -> dict:
    if status not in ("pending", "done", "cancelled"):
        raise ValueError("Elle yalnızca pending / done / cancelled yapılabilir.")
    ts = now_iso()
    with db.tx() as t:
        row = t.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise KeyError("Görev yok")
        if row["status"] == "running":
            raise ValueError("Çalışan görevin durumu elle değiştirilemez.")
        t.execute(
            "UPDATE tasks SET status=?, updated_at=?, finished_at=?, attempts=CASE WHEN ?='pending' THEN 0 ELSE attempts END, "
            "next_run_at=NULL, output=COALESCE(?, output) WHERE id=?",
            (status, ts, ts if status in ("done", "cancelled") else None, status, note, task_id),
        )
    log_activity(db, "task_status", f"Görev #{task_id} → {status}", ref=f"task:{task_id}")
    return get(db, task_id)


def counts(db: Database) -> dict:
    rows = db.query("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status")
    return {s: 0 for s in STATUSES} | {r["status"]: r["n"] for r in rows}


def summary_for_prompt(db: Database) -> str:
    rows = db.query("SELECT t.id, t.title, t.status, t.priority, p.slug FROM tasks t LEFT JOIN projects p ON p.id=t.project_id "
                    "WHERE t.status IN ('pending','waiting_approval','running','failed') ORDER BY t.priority, t.id LIMIT 15")
    done = db.query("SELECT id, title FROM tasks WHERE status='done' AND finished_at >= ? ORDER BY finished_at DESC LIMIT 8",
                    ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds"),))
    lines = [f"- #{r['id']} [{r['status']}, P{r['priority']}, {r['slug'] or '-'}] {r['title']}" for r in rows]
    if done:
        lines.append("Son 24 saatte tamamlananlar: " + "; ".join(f"#{d['id']} {d['title']}" for d in done))
    return "\n".join(lines)


# ---------------- yürütücü ----------------

class TaskWorker:
    def __init__(self, db: Database, router: LLMRouter, poll_seconds: float = 5.0):
        self.db = db
        self.router = router
        self.poll_seconds = poll_seconds
        self._stop = asyncio.Event()

    def claim_next(self) -> dict | None:
        ts = now_iso()
        with self.db.tx() as t:
            row = t.execute(
                "SELECT id FROM tasks WHERE status='pending' AND kind != 'manual' "
                "AND (next_run_at IS NULL OR next_run_at <= ?) ORDER BY priority, id LIMIT 1", (ts,)).fetchone()
            if not row:
                return None
            cur = t.execute(
                "UPDATE tasks SET status='running', locked_by=?, locked_at=?, last_run_at=?, attempts=attempts+1, "
                "updated_at=? WHERE id=? AND status='pending'", (WORKER_ID, ts, ts, ts, row["id"]))
            if cur.rowcount != 1:
                return None
        return get(self.db, row["id"])

    def _estimate_try(self, task: dict) -> float | None:
        chain = self.router.chain("smart" if task["kind"] == "plan" else "fast")
        for r in chain:
            p = self.router.providers.get(r.provider)
            if p and p.available():
                price = p.price(p.resolve_model(r.model) if hasattr(p, "resolve_model") else r.model)
                usd = cost_usd(price, len(task["description"] + task["title"]) // 3 + 1500, 4096)
                rate = self.router.settings.usd_try_rate
                return usd * rate if (usd is not None and rate) else None
        return None

    async def run_one(self) -> dict | None:
        task = self.claim_next()
        if not task:
            return None
        tid = task["id"]
        try:
            est = self._estimate_try(task)
            if est is not None:
                with self.db.tx() as t:
                    t.execute("UPDATE tasks SET estimated_cost_usd=? WHERE id=?", (est / self.router.settings.usd_try_rate, tid))
            needs_approval = est is not None and est > APPROVAL_THRESHOLD_TRY
            approved = self.db.one("SELECT 1 AS x FROM approvals WHERE task_id=? AND action='spend_money' "
                                   "AND status IN ('approved','executed')", (tid,))
            if needs_approval and not approved:
                with self.db.tx() as t:
                    t.execute("UPDATE tasks SET status='waiting_approval', locked_by=NULL, attempts=attempts-1, updated_at=? "
                              "WHERE id=?", (now_iso(), tid))
                approvals.request(self.db, "spend_money", f"Görev #{tid} tahmini ≈{est:.2f} TL harcayacak: {task['title']}",
                                  {"task_id": tid, "estimated_try": round(est, 2)}, task_id=tid)
                return get(self.db, tid)
            output = await self._execute(task)
            ts = now_iso()
            with self.db.tx() as t:
                t.execute("UPDATE tasks SET status='done', output=?, last_error=NULL, locked_by=NULL, finished_at=?, updated_at=? "
                          "WHERE id=?", (output, ts, ts, tid))
            log_activity(self.db, "task_done", f"Görev tamamlandı: {task['title']}", ref=f"task:{tid}")
        except Exception as e:  # noqa: BLE001 — her hata kaydedilmeli
            self._fail(task, e)
        return get(self.db, tid)

    def _fail(self, task: dict, e: Exception) -> None:
        tid = task["id"]
        msg = f"{type(e).__name__}: {e}"[:1000]
        permanent = isinstance(e, (BudgetError, NoProviderError, ValueError)) or (
            isinstance(e, ProvidersFailed) and not e.retryable)
        ts = now_iso()
        if permanent or task["attempts"] >= task["max_attempts"]:
            with self.db.tx() as t:
                t.execute("UPDATE tasks SET status='failed', last_error=?, locked_by=NULL, finished_at=?, updated_at=? WHERE id=?",
                          (msg, ts, ts, tid))
            log_activity(self.db, "task_failed", f"Görev başarısız: {task['title']}", detail=msg, ref=f"task:{tid}", level="error")
        else:
            delay = 30 * (2 ** (task["attempts"] - 1))
            nxt = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(timespec="seconds")
            with self.db.tx() as t:
                t.execute("UPDATE tasks SET status='pending', last_error=?, locked_by=NULL, next_run_at=?, updated_at=? WHERE id=?",
                          (msg, nxt, ts, tid))
            log_activity(self.db, "task_retry", f"Görev #{tid} yeniden denenecek ({delay} sn sonra)", detail=msg,
                         ref=f"task:{tid}", level="warn")

    async def _execute(self, task: dict) -> str:
        from .persona import PERSONA
        if task["kind"] == "llm":
            res, _ = await self.router.complete(
                system=PERSONA + "\nŞu an arka planda bir görev yürütüyorsun. Sonucu doğrudan, kullanılabilir biçimde yaz.",
                messages=[{"role": "user", "content": f"Görev: {task['title']}\n\n{task['description']}".strip()}],
                tier="fast", purpose=f"task:{task['id']}")
            return res.text
        if task["kind"] == "plan":
            res, _ = await self.router.complete(
                system=PERSONA + "\nBir hedefi 3-8 somut, uygulanabilir alt göreve ayır. YALNIZCA JSON dizi döndür: "
                                 '[{"title": "...", "priority": 1-5, "kind": "manual" | "llm"}]. '
                                 '"llm" yalnızca metin üretimi/analizle bitebilecek işler içindir.',
                messages=[{"role": "user", "content": f"Hedef: {task['title']}\n\n{task['description']}".strip()}],
                tier="smart", purpose=f"plan:{task['id']}", max_tokens=4096)
            items = parse_plan(res.text)
            if not items:
                raise ValueError("Plan çıktısı ayrıştırılamadı")
            created = []
            for it in items[:8]:
                sub = create(self.db, it["title"], kind=it.get("kind", "manual") if it.get("kind") in ("manual", "llm") else "manual",
                             project_id=task["project_id"], priority=it.get("priority", 3), origin="goal", parent_id=task["id"],
                             dedupe_key=f"plan:{task['id']}:{it['title'][:80].lower()}")
                created.append(f"#{sub['id']} {sub['title']}")
            return "Alt görevler:\n" + "\n".join(created)
        raise ValueError(f"Yürütülemeyen görev türü: {task['kind']}")

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                did = await self.run_one()
            except Exception as e:  # noqa: BLE001
                log_activity(self.db, "worker_error", "Görev işçisi hatası", detail=str(e)[:500], level="error")
                did = None
            if did is None:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
                except asyncio.TimeoutError:
                    pass

    def stop(self) -> None:
        self._stop.set()


def parse_plan(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, flags=re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    for it in data if isinstance(data, list) else []:
        if isinstance(it, dict) and isinstance(it.get("title"), str) and it["title"].strip():
            try:
                pr = int(it.get("priority", 3))
            except (TypeError, ValueError):
                pr = 3
            out.append({"title": it["title"].strip()[:200], "priority": pr, "kind": it.get("kind", "manual")})
    return out
