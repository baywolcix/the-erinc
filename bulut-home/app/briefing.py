"""Günlük brifing: veritabanındaki gerçek verilerden rapor.

- Veri her zaman deterministik toplanır (uydurma yok).
- Model erişilebilir ve bütçe uygunsa kısa, okunabilir bir metne çevrilir; değilse deterministik metin kullanılır.
- Zamanlayıcı her gün ayarlanan yerel saatte bir 'brief' görevi açar (dedupe: günde bir).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import tasks
from .db import Database, now_iso, log_activity
from .llm.router import BudgetError, LLMRouter, NoProviderError, ProvidersFailed


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def collect(db: Database, tz: str = "Europe/Istanbul", now: datetime | None = None) -> dict:
    """Son 24 saat + açık işler. Zaman damgaları UTC saklanır, gün sınırı yerel saate göre."""
    z = ZoneInfo(tz)
    now = (now or datetime.now(timezone.utc)).astimezone(z)
    since = now - timedelta(hours=24)
    s = _utc(since)
    done = db.query("SELECT t.id, t.title, p.slug AS project FROM tasks t LEFT JOIN projects p ON p.id=t.project_id "
                    "WHERE t.status='done' AND t.kind!='brief' AND t.finished_at>=? ORDER BY t.finished_at", (s,))
    failed = db.query("SELECT t.id, t.title, t.last_error, p.slug AS project FROM tasks t LEFT JOIN projects p ON p.id=t.project_id "
                      "WHERE t.status='failed' AND t.kind!='brief' AND t.finished_at>=? ORDER BY t.finished_at", (s,))
    open_ = db.query("SELECT t.id, t.title, t.status, t.priority, p.slug AS project FROM tasks t LEFT JOIN projects p ON p.id=t.project_id "
                     "WHERE t.status IN ('pending','running','waiting_approval') AND t.kind!='brief' ORDER BY t.priority, t.id LIMIT 15")
    cost = db.one("SELECT COALESCE(SUM(cost_usd),0) AS usd, COUNT(*) AS calls, COALESCE(SUM(1-ok),0) AS errors "
                  "FROM llm_calls WHERE created_at>=?", (s,))
    month = db.one("SELECT COALESCE(SUM(cost_usd),0) AS usd FROM llm_calls WHERE created_at>=?",
                   (_utc(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)),))
    projects = db.query(
        "SELECT p.slug, p.name, p.status, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.status='done') AS done, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id) AS total FROM projects p WHERE p.status='active' ORDER BY p.id")
    approvals_pending = db.query("SELECT id, summary FROM approvals WHERE status='pending' ORDER BY id")
    new_mem = db.one("SELECT COUNT(*) AS n FROM memories WHERE created_at>=?", (s,))["n"]
    msgs = db.one("SELECT COUNT(*) AS n FROM messages WHERE created_at>=? AND role='user'", (s,))["n"]
    web = db.one("SELECT COUNT(DISTINCT url) AS n FROM web_sources WHERE fetched_at>=? AND url IS NOT NULL", (s,))["n"]
    return {
        "generated_at": now.isoformat(timespec="minutes"),
        "window": "son 24 saat",
        "tasks_done": done, "tasks_failed": failed, "tasks_open": open_,
        "ai_cost_usd_24h": round(cost["usd"], 6), "ai_calls_24h": cost["calls"], "ai_errors_24h": cost["errors"],
        "ai_cost_usd_month": round(month["usd"], 6),
        "projects": projects, "approvals_pending": approvals_pending,
        "new_memories_24h": new_mem, "user_messages_24h": msgs, "web_sources_24h": web,
    }


def render(data: dict, usd_try: float | None) -> str:
    def money(usd: float) -> str:
        return f"{usd * usd_try:.2f} TL" if usd_try else f"${usd:.4f}"
    L = [f"Günlük brifing — {data['generated_at'][:10]} ({data['window']})", ""]
    L.append(f"Tamamlanan: {len(data['tasks_done'])} · Başarısız: {len(data['tasks_failed'])} · Açık: {len(data['tasks_open'])}")
    for t in data["tasks_done"][:8]:
        L.append(f"  ✓ #{t['id']} {t['title']}")
    for t in data["tasks_failed"][:5]:
        L.append(f"  ✗ #{t['id']} {t['title']} — {(t['last_error'] or '')[:120]}")
    if data["approvals_pending"]:
        L.append(f"Onay bekleyen: {len(data['approvals_pending'])}")
        for a in data["approvals_pending"][:5]:
            L.append(f"  • #{a['id']} {a['summary']}")
    if data["projects"]:
        L.append("Projeler: " + " · ".join(f"{p['name']} {p['done']}/{p['total']}" for p in data["projects"]))
    L.append(f"AI kullanımı: {data['ai_calls_24h']} çağrı, {money(data['ai_cost_usd_24h'])} (bu ay {money(data['ai_cost_usd_month'])})"
             + (f", {data['ai_errors_24h']} hata" if data["ai_errors_24h"] else ""))
    if data["tasks_open"]:
        L.append("Bugünün öncelikleri:")
        for t in data["tasks_open"][:5]:
            L.append(f"  → P{t['priority']} #{t['id']} {t['title']}" + (f" [{t['project']}]" if t["project"] else ""))
    else:
        L.append("Açık görev yok.")
    return "\n".join(L)


BRIEF_SYSTEM = """Sen BULUT'sun. Sana verilen JSON, sahibinin son 24 saatine ait GERÇEK kayıtlardır.
Bundan Türkçe, kısa (en fazla ~180 kelime), sakin ve net bir sabah brifingi yaz:
1) Dün ne bitti / ne takıldı, 2) dikkat gerektirenler (başarısız görev, bekleyen onay, maliyet), 3) bugün için en fazla 3 öncelik.
JSON'da olmayan hiçbir iş, sayı veya olay uydurma. Veri azsa bunu açıkça söyle. Başlık veya giriş cümlesi kullanma."""


async def generate(db: Database, router: LLMRouter | None, tz: str, usd_try: float | None,
                   day: str | None = None, use_llm: bool = True) -> dict:
    data = collect(db, tz)
    day = day or data["generated_at"][:10]
    text, source, note, call_id = render(data, usd_try), "deterministic", None, None
    if use_llm and router is not None:
        try:
            res, call_id = await router.complete(system=BRIEF_SYSTEM, tier="fast", purpose=f"brief:{day}", max_tokens=1500,
                                                 messages=[{"role": "user", "content": json.dumps(data, ensure_ascii=False)}])
            if res.text.strip():
                text, source = res.text.strip(), "llm"
        except (BudgetError, NoProviderError, ProvidersFailed) as e:
            note = f"Model kullanılmadı: {e}"
    with db.tx() as t:
        t.execute("INSERT INTO briefings(day,content,data,source,note,llm_call_id,created_at) VALUES (?,?,?,?,?,?,?) "
                  "ON CONFLICT(day) DO UPDATE SET content=excluded.content, data=excluded.data, source=excluded.source, "
                  "note=excluded.note, llm_call_id=excluded.llm_call_id, created_at=excluded.created_at",
                  (day, text, json.dumps(data, ensure_ascii=False), source, note, call_id, now_iso()))
    log_activity(db, "briefing", f"Günlük brifing hazırlandı ({day}, {'model' if source == 'llm' else 'veri özeti'})",
                 detail=note, ref=f"briefing:{day}")
    return db.one("SELECT * FROM briefings WHERE day=?", (day,))


def maybe_schedule(db: Database, brief_time: str, tz: str, now: datetime | None = None) -> dict | None:
    """Yerel saat brief_time'ı geçtiyse ve bugünün brifingi yoksa bir 'brief' görevi açar (günde bir)."""
    if not brief_time:
        return None
    try:
        hh, mm = (int(x) for x in brief_time.split(":"))
    except ValueError:
        return None
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz))
    if (local.hour, local.minute) < (hh, mm):
        return None
    day = local.strftime("%Y-%m-%d")
    if db.one("SELECT 1 AS x FROM briefings WHERE day=?", (day,)):
        return None
    if db.one("SELECT 1 AS x FROM tasks WHERE dedupe_key=?", (f"brief:{day}",)):
        return None  # bugün zaten denendi (başarısız olsa bile tekrar tekrar açma)
    return tasks.create(db, f"Günlük brifing {day}", kind="brief", priority=2, origin="proposed",
                        dedupe_key=f"brief:{day}", max_attempts=2)
