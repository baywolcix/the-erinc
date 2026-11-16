"""Bildirimler: uygulama içi kutu + mobil kanallar (ntfy, Telegram).

- Her olay `notifications` tablosuna yazılır (uygulama içi her zaman).
- Mobil teslimat `notification_deliveries` kuyruğundan yapılır: yeniden başlatmada kaybolmaz,
  başarısızlıkta 1/5/30 dk geri çekilerek en fazla 4 deneme.
- `dedupe_key` aynı olayın iki kez bildirilmesini engeller (ör. ayda bir bütçe uyarısı).
- Sessiz saatlerde yalnızca 'critical' anında gider; diğerleri sessiz saat bitince.
- Metinler gönderilmeden önce gizli değer maskelemesinden geçer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .db import Database, now_iso
from .redact import redact

LEVELS = {"info": 1, "important": 2, "critical": 3}
RETRY_DELAYS = [60, 300, 1800]
MAX_ATTEMPTS = 4


@dataclass
class NotifyConfig:
    ntfy_url: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_token: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    min_level: str = "important"
    details: bool = True
    quiet: str = ""                 # "23:00-08:00"
    timezone: str = "Europe/Istanbul"
    public_url: str = ""
    transport: object = field(default=None, repr=False)  # testler için httpx2 transport

    def channels(self) -> list[str]:
        ch = []
        if self.ntfy_topic:
            ch.append("ntfy")
        if self.telegram_bot_token and self.telegram_chat_id:
            ch.append("telegram")
        return ch


_config = NotifyConfig()


def configure(cfg: NotifyConfig) -> None:
    global _config
    _config = cfg


def config() -> NotifyConfig:
    return _config


def notify(db: Database, event: str, title: str, body: str = "", level: str = "info", ref: str | None = None,
           dedupe_key: str | None = None) -> int | None:
    """Bildirim oluştur. Aynı dedupe_key varsa None döner (tekrar yok)."""
    level = level if level in LEVELS else "info"
    cfg = _config
    with db.tx() as t:
        cur = t.execute(
            "INSERT INTO notifications(event,level,title,body,ref,dedupe_key,created_at) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(dedupe_key) DO NOTHING",
            (event, level, redact(title)[:200], redact(body)[:2000], ref, dedupe_key, now_iso()))
        if cur.rowcount == 0:
            return None
        nid = cur.lastrowid
        if LEVELS[level] >= LEVELS.get(cfg.min_level, 2):
            for ch in cfg.channels():
                t.execute("INSERT INTO notification_deliveries(notification_id,channel,status,attempts,next_attempt_at) "
                          "VALUES (?,?, 'pending', 0, ?)", (nid, ch, now_iso()))
    return nid


def _in_quiet(cfg: NotifyConfig, now: datetime) -> datetime | None:
    """Sessiz saatteyse bitiş zamanını (UTC) döndür."""
    if not cfg.quiet or "-" not in cfg.quiet:
        return None
    try:
        a, b = cfg.quiet.split("-")
        ah, am = (int(x) for x in a.split(":"))
        bh, bm = (int(x) for x in b.split(":"))
    except ValueError:
        return None
    local = now.astimezone(ZoneInfo(cfg.timezone))
    start = local.replace(hour=ah, minute=am, second=0, microsecond=0)
    end = local.replace(hour=bh, minute=bm, second=0, microsecond=0)
    if start <= end:
        inside = start <= local < end
    else:  # gece yarısını aşan aralık
        inside = local >= start or local < end
        if local >= start:
            end += timedelta(days=1)
    return end.astimezone(timezone.utc) if inside else None


def _text(cfg: NotifyConfig, n: dict) -> tuple[str, str]:
    title = n["title"]
    body = n["body"] if cfg.details else "Ayrıntılar BULUT HOME'da."
    if not cfg.details and n["ref"]:
        body = f"{body} ({n['ref']})"
    return title, body


async def _send(cfg: NotifyConfig, channel: str, n: dict) -> None:
    import httpx2
    title, body = _text(cfg, n)
    async with httpx2.AsyncClient(timeout=15.0, transport=cfg.transport) as c:
        if channel == "ntfy":
            payload = {"topic": cfg.ntfy_topic, "title": title, "message": body or title,
                       "priority": {"info": 3, "important": 4, "critical": 5}[n["level"]],
                       "tags": {"info": ["cloud"], "important": ["bell"], "critical": ["warning"]}[n["level"]]}
            if cfg.public_url:
                payload["click"] = cfg.public_url
            headers = {"Authorization": f"Bearer {cfg.ntfy_token}"} if cfg.ntfy_token else {}
            r = await c.post(cfg.ntfy_url.rstrip("/"), json=payload, headers=headers)
        elif channel == "telegram":
            text = f"{title}\n{body}".strip() + (f"\n{cfg.public_url}" if cfg.public_url else "")
            r = await c.post(f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage",
                             json={"chat_id": cfg.telegram_chat_id, "text": text[:4000], "disable_web_page_preview": True})
        else:
            raise ValueError(f"bilinmeyen kanal {channel}")
    if r.status_code >= 400:
        raise RuntimeError(f"{channel} HTTP {r.status_code}: {r.text[:200]}")


async def deliver_pending(db: Database, now: datetime | None = None, limit: int = 20) -> dict:
    cfg = _config
    now = now or datetime.now(timezone.utc)
    rows = db.query(
        "SELECT d.id AS did, d.channel, d.attempts, n.* FROM notification_deliveries d JOIN notifications n ON n.id=d.notification_id "
        "WHERE d.status='pending' AND d.next_attempt_at<=? ORDER BY d.id LIMIT ?", (now.isoformat(timespec="seconds"), limit))
    stats = {"sent": 0, "failed": 0, "deferred": 0, "retry": 0}
    quiet_end = _in_quiet(cfg, now)
    for r in rows:
        if r["channel"] not in cfg.channels():
            with db.tx() as t:
                t.execute("UPDATE notification_deliveries SET status='skipped', last_error='kanal artık yapılandırılmamış' WHERE id=?", (r["did"],))
            continue
        if quiet_end and r["level"] != "critical":
            with db.tx() as t:
                t.execute("UPDATE notification_deliveries SET next_attempt_at=? WHERE id=?",
                          (quiet_end.isoformat(timespec="seconds"), r["did"]))
            stats["deferred"] += 1
            continue
        try:
            await _send(cfg, r["channel"], r)
            with db.tx() as t:
                t.execute("UPDATE notification_deliveries SET status='sent', attempts=attempts+1, sent_at=?, last_error=NULL WHERE id=?",
                          (now_iso(), r["did"]))
            stats["sent"] += 1
        except Exception as e:  # noqa: BLE001 — teslimat hatası kaydedilir, uygulama etkilenmez
            attempts = r["attempts"] + 1
            err = redact(f"{type(e).__name__}: {e}")[:500]
            if attempts >= MAX_ATTEMPTS:
                with db.tx() as t:
                    t.execute("UPDATE notification_deliveries SET status='failed', attempts=?, last_error=? WHERE id=?",
                              (attempts, err, r["did"]))
                stats["failed"] += 1
            else:
                nxt = (now + timedelta(seconds=RETRY_DELAYS[min(attempts - 1, len(RETRY_DELAYS) - 1)])).isoformat(timespec="seconds")
                with db.tx() as t:
                    t.execute("UPDATE notification_deliveries SET attempts=?, last_error=?, next_attempt_at=? WHERE id=?",
                              (attempts, err, nxt, r["did"]))
                stats["retry"] += 1
    return stats


def list_notifications(db: Database, unread_only: bool = False, limit: int = 50) -> dict:
    where = "WHERE read_at IS NULL" if unread_only else ""
    items = db.query(f"SELECT * FROM notifications {where} ORDER BY id DESC LIMIT ?", (limit,))
    if items:
        ids = [i["id"] for i in items]
        q = ",".join("?" * len(ids))
        deliveries = db.query(f"SELECT notification_id, channel, status, attempts, last_error FROM notification_deliveries "
                              f"WHERE notification_id IN ({q})", tuple(ids))
        by = {}
        for d in deliveries:
            by.setdefault(d["notification_id"], []).append(d)
        for i in items:
            i["deliveries"] = by.get(i["id"], [])
    unread = db.one("SELECT COUNT(*) AS n FROM notifications WHERE read_at IS NULL")["n"]
    return {"items": items, "unread": unread, "channels": _config.channels(), "min_level": _config.min_level}


def mark_read(db: Database, nid: int | None = None) -> int:
    with db.tx() as t:
        if nid is None:
            return t.execute("UPDATE notifications SET read_at=? WHERE read_at IS NULL", (now_iso(),)).rowcount
        return t.execute("UPDATE notifications SET read_at=? WHERE id=? AND read_at IS NULL", (now_iso(), nid)).rowcount


def budget_check(db: Database, spent_try: float | None, budget_try: float) -> None:
    """Aylık bütçenin %80'i ve %100'ü için ayda bir bildirim."""
    if spent_try is None or budget_try <= 0:
        return
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    ratio = spent_try / budget_try
    if ratio >= 1.0:
        notify(db, "budget_blocked", "Aylık API bütçesi doldu", f"Harcanan ≈{spent_try:.2f} / {budget_try:.0f} TL. Ücretli çağrılar durdu.",
               "critical", "system:budget", dedupe_key=f"budget100:{month}")
    elif ratio >= 0.8:
        notify(db, "budget_warning", "API bütçesinin %80'i kullanıldı", f"Harcanan ≈{spent_try:.2f} / {budget_try:.0f} TL.",
               "important", "system:budget", dedupe_key=f"budget80:{month}")
