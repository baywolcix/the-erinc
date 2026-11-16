"""Genel zamanlanmış görevler.

Biçimler (yerel saat, BULUT_TIMEZONE):
  daily 08:30                 her gün
  weekly mon,thu 09:00        haftanın günleri (mon..sun veya pzt,sal,car,per,cum,cmt,paz)
  monthly 1 10:00             ayın günü (1-28)
  every 6h | every 30m        aralık (en az 15 dk, en fazla 7 gün)

Garantiler:
- Zamanlamalar DB'de; yeniden başlatmada kaybolmaz.
- (schedule_id, slot) birincil anahtarı: aynı planlı çalışma iki kez görev üretmez.
- Önceki çalışmanın görevi hâlâ aktifse yeni görev açılmaz ('skipped_active') → yığılma yok.
- Kapalı kalınan sürede kaçırılan çalışmalar için en fazla BİR görev açılır, sonra gelecek zamana atlanır.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import approvals, tasks
from .db import Database, now_iso, log_activity

DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
        "pzt": 0, "sal": 1, "car": 2, "çar": 2, "per": 3, "cum": 4, "cmt": 5, "paz": 6}
DAY_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
KINDS = ("manual", "llm", "plan")
MIN_INTERVAL = timedelta(minutes=15)


def _hm(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", s)
    if not m:
        raise ValueError(f"Saat HH:MM biçiminde olmalı: {s}")
    return int(m.group(1)), int(m.group(2))


def parse(spec: str) -> dict:
    parts = spec.strip().lower().split()
    if not parts:
        raise ValueError("Zamanlama boş")
    kind = parts[0]
    if kind == "daily" and len(parts) == 2:
        h, m = _hm(parts[1])
        return {"type": "daily", "h": h, "m": m}
    if kind == "weekly" and len(parts) == 3:
        days = []
        for d in parts[1].split(","):
            if d not in DAYS:
                raise ValueError(f"Bilinmeyen gün: {d}")
            days.append(DAYS[d])
        h, m = _hm(parts[2])
        return {"type": "weekly", "days": sorted(set(days)), "h": h, "m": m}
    if kind == "monthly" and len(parts) == 3:
        if not parts[1].isdigit() or not 1 <= int(parts[1]) <= 28:
            raise ValueError("Ayın günü 1-28 olmalı")
        h, m = _hm(parts[2])
        return {"type": "monthly", "day": int(parts[1]), "h": h, "m": m}
    if kind == "every" and len(parts) == 2:
        m = re.fullmatch(r"(\d+)([mh])", parts[1])
        if not m:
            raise ValueError("Aralık biçimi: every 30m | every 6h")
        delta = timedelta(minutes=int(m.group(1))) if m.group(2) == "m" else timedelta(hours=int(m.group(1)))
        if delta < MIN_INTERVAL or delta > timedelta(days=7):
            raise ValueError("Aralık 15 dakika ile 7 gün arasında olmalı")
        return {"type": "every", "seconds": int(delta.total_seconds())}
    raise ValueError("Geçersiz zamanlama. Örnekler: 'daily 08:30', 'weekly mon,thu 09:00', 'monthly 1 10:00', 'every 6h'")


def describe(spec: str) -> str:
    p = parse(spec)
    if p["type"] == "daily":
        return f"Her gün {p['h']:02d}:{p['m']:02d}"
    if p["type"] == "weekly":
        return f"Her {', '.join(DAY_TR[d] for d in p['days'])} {p['h']:02d}:{p['m']:02d}"
    if p["type"] == "monthly":
        return f"Her ayın {p['day']}. günü {p['h']:02d}:{p['m']:02d}"
    s = p["seconds"]
    return f"Her {s // 3600} saatte bir" if s % 3600 == 0 else f"Her {s // 60} dakikada bir"


def next_after(spec: str, after: datetime, tz: str) -> datetime:
    """`after`dan kesinlikle SONRAKİ ilk çalışma zamanı (UTC)."""
    p = parse(spec)
    z = ZoneInfo(tz)
    if p["type"] == "every":
        return (after + timedelta(seconds=p["seconds"])).astimezone(timezone.utc).replace(microsecond=0)
    local = after.astimezone(z)
    for i in range(0, 400):
        day = (local + timedelta(days=i)).date()
        if p["type"] == "weekly" and day.weekday() not in p["days"]:
            continue
        if p["type"] == "monthly" and day.day != p["day"]:
            continue
        cand = datetime(day.year, day.month, day.day, p["h"], p["m"], tzinfo=z)
        if cand > local:
            return cand.astimezone(timezone.utc)
    raise ValueError("Sonraki çalışma zamanı bulunamadı")


def upcoming(spec: str, tz: str, n: int = 3, now: datetime | None = None) -> list[str]:
    t = now or datetime.now(timezone.utc)
    out = []
    for _ in range(n):
        t = next_after(spec, t, tz)
        out.append(t.isoformat(timespec="seconds"))
    return out


def create(db: Database, name: str, spec: str, title: str, task_kind: str = "manual", description: str = "",
           project_id: int | None = None, priority: int = 3, created_by: str = "user", enabled: bool = True,
           tz: str = "Europe/Istanbul") -> dict:
    name, title = name.strip()[:120], title.strip()[:300]
    if not name or not title:
        raise ValueError("Ad ve görev başlığı gerekli")
    if task_kind not in KINDS:
        raise ValueError(f"Görev türü: {', '.join(KINDS)}")
    parse(spec)
    nxt = next_after(spec, datetime.now(timezone.utc), tz).isoformat(timespec="seconds")
    with db.tx() as t:
        sid = t.execute(
            "INSERT INTO schedules(name,spec,task_kind,title,description,project_id,priority,enabled,next_run_at,created_by,"
            "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, spec.strip().lower(), task_kind, title, description[:4000], project_id, max(1, min(5, int(priority))),
             1 if enabled else 0, nxt, created_by, now_iso(), now_iso())).lastrowid
    log_activity(db, "schedule_created", f"Zamanlama oluşturuldu: {name} ({describe(spec)})", ref=f"schedule:{sid}")
    return get(db, sid)


def get(db: Database, sid: int) -> dict | None:
    s = db.one("SELECT s.*, p.slug AS project_slug FROM schedules s LEFT JOIN projects p ON p.id=s.project_id WHERE s.id=?", (sid,))
    if s:
        s["description_human"] = describe(s["spec"])
    return s


def list_all(db: Database) -> list[dict]:
    rows = db.query("SELECT s.*, p.slug AS project_slug, (SELECT status FROM tasks t WHERE t.id=s.last_task_id) AS last_task_status "
                    "FROM schedules s LEFT JOIN projects p ON p.id=s.project_id ORDER BY s.enabled DESC, s.next_run_at")
    for r in rows:
        r["description_human"] = describe(r["spec"])
    return rows


def update(db: Database, sid: int, tz: str, **fields) -> dict:
    s = get(db, sid)
    if not s:
        raise KeyError("Zamanlama yok")
    allowed = {k: v for k, v in fields.items() if k in ("name", "spec", "title", "description", "priority", "enabled", "task_kind")
               and v is not None}
    if "spec" in allowed:
        parse(allowed["spec"])
        allowed["spec"] = allowed["spec"].strip().lower()
    if "task_kind" in allowed and allowed["task_kind"] not in KINDS:
        raise ValueError(f"Görev türü: {', '.join(KINDS)}")
    if "enabled" in allowed:
        allowed["enabled"] = 1 if allowed["enabled"] else 0
    if "spec" in allowed or allowed.get("enabled") == 1:
        allowed["next_run_at"] = next_after(allowed.get("spec", s["spec"]), datetime.now(timezone.utc), tz).isoformat(timespec="seconds")
    if allowed:
        allowed["updated_at"] = now_iso()
        with db.tx() as t:
            t.execute(f"UPDATE schedules SET {', '.join(f'{k}=?' for k in allowed)} WHERE id=?", (*allowed.values(), sid))
    return get(db, sid)


def delete(db: Database, sid: int) -> bool:
    with db.tx() as t:
        return t.execute("DELETE FROM schedules WHERE id=?", (sid,)).rowcount > 0


def tick(db: Database, tz: str, now: datetime | None = None) -> list[dict]:
    """Vakti gelen zamanlamalar için görev aç. Dönen liste: oluşturulan/atlanan çalışmalar."""
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    now_s = now.isoformat(timespec="seconds")
    due = db.query("SELECT id FROM schedules WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=? ORDER BY next_run_at",
                   (now_s,))
    out = []
    for row in due:
        with db.tx() as t:
            s = t.execute("SELECT * FROM schedules WHERE id=? AND enabled=1 AND next_run_at<=?", (row["id"], now_s)).fetchone()
            if not s:
                continue
            s = dict(s)
            slot = s["next_run_at"]
            nxt = next_after(s["spec"], now, tz).isoformat(timespec="seconds")
            try:
                t.execute("INSERT INTO schedule_runs(schedule_id,slot,status,created_at) VALUES (?,?, 'pending', ?)",
                          (s["id"], slot, now_iso()))
            except sqlite3.IntegrityError:
                t.execute("UPDATE schedules SET next_run_at=? WHERE id=?", (nxt, s["id"]))
                continue  # bu slot zaten işlendi
            active = t.execute("SELECT 1 FROM tasks WHERE id=? AND status IN ('pending','running','waiting_approval')",
                               (s["last_task_id"],)).fetchone() if s["last_task_id"] else None
            if active:
                status, task_id = "skipped_active", None
            else:
                task = tasks.create(db, s["title"], s["description"], kind=s["task_kind"], project_id=s["project_id"],
                                    priority=s["priority"], origin="proposed", dedupe_key=f"sched:{s['id']}:{slot}")
                status, task_id = "created", task["id"]
            t.execute("UPDATE schedule_runs SET status=?, task_id=? WHERE schedule_id=? AND slot=?", (status, task_id, s["id"], slot))
            t.execute("UPDATE schedules SET next_run_at=?, last_run_at=?, last_task_id=COALESCE(?, last_task_id), updated_at=? WHERE id=?",
                      (nxt, now_s, task_id, now_iso(), s["id"]))
        out.append({"schedule_id": s["id"], "slot": slot, "status": status, "task_id": task_id, "next_run_at": nxt})
        if status == "skipped_active":
            log_activity(db, "schedule_skipped", f"Zamanlama '{s['name']}' atlandı: önceki görev hâlâ açık",
                         ref=f"schedule:{s['id']}", level="warn")
    return out


@approvals.executor("enable_schedule")
def _exec_enable(db: Database, payload: dict) -> str:
    sid = int(payload["schedule_id"])
    s = get(db, sid)
    if not s:
        return f"Zamanlama #{sid} yok"
    update(db, sid, payload.get("tz", "Europe/Istanbul"), enabled=True)
    return f"Zamanlama #{sid} etkinleştirildi"
