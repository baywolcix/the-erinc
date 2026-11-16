"""Sohbet servisi: kısa dönem (son mesajlar) + uzun dönem (hafıza) bağlam, işaret ayrıştırma."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from . import memory, tasks
from .db import Database, now_iso, log_activity
from .llm.router import LLMRouter, choose_tier
from .persona import build_system

SHORT_TERM_MESSAGES = 20
_MEM_RE = re.compile(r"\[\[HATIRLA:([a-z]+)\|(.+?)\]\]", re.S)
_TASK_RE = re.compile(r"\[\[GOREV:([1-5])\|([^|\]]*)\|(.+?)\]\]", re.S)
TZ = ZoneInfo("Europe/Istanbul")


def ensure_conversation(db: Database, conv_id: int | None, first_text: str) -> int:
    if conv_id:
        if db.one("SELECT id FROM conversations WHERE id=?", (conv_id,)):
            return conv_id
        raise KeyError("Konuşma bulunamadı")
    title = re.sub(r"\s+", " ", first_text).strip()[:60] or "Yeni konuşma"
    with db.tx() as t:
        return t.execute("INSERT INTO conversations(title,created_at,updated_at) VALUES (?,?,?)",
                         (title, now_iso(), now_iso())).lastrowid


def add_message(db: Database, conv_id: int, role: str, content: str, model: str | None = None,
                llm_call_id: int | None = None) -> dict:
    with db.tx() as t:
        mid = t.execute("INSERT INTO messages(conversation_id,role,content,model,llm_call_id,created_at) VALUES (?,?,?,?,?,?)",
                        (conv_id, role, content, model, llm_call_id, now_iso())).lastrowid
        t.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now_iso(), conv_id))
    return db.one("SELECT * FROM messages WHERE id=?", (mid,))


def extract_markers(text: str) -> tuple[str, list[tuple[str, str]], list[tuple[int, str, str]]]:
    mems = [(k.strip(), v.strip()) for k, v in _MEM_RE.findall(text)][:3]
    tsk = [(int(p), s.strip(), t.strip()) for p, s, t in _TASK_RE.findall(text)][:3]
    clean = _TASK_RE.sub("", _MEM_RE.sub("", text)).strip()
    return clean, mems, tsk


async def reply(db: Database, router: LLMRouter, conv_id: int | None, text: str, tier: str | None = None) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("Boş mesaj")
    if len(text) > 20000:
        raise ValueError("Mesaj çok uzun (en fazla 20.000 karakter)")
    conv_id = ensure_conversation(db, conv_id, text)
    user_msg = add_message(db, conv_id, "user", text)

    history = db.query(
        "SELECT role, content FROM (SELECT id, role, content FROM messages WHERE conversation_id=? AND role IN ('user','assistant') "
        "ORDER BY id DESC LIMIT ?) ORDER BY id", (conv_id, SHORT_TERM_MESSAGES))
    # API ilk mesajın kullanıcı olmasını ister
    while history and history[0]["role"] != "user":
        history.pop(0)
    mems = memory.recall(db, text)
    projects = db.query("SELECT slug, name, status, description FROM projects ORDER BY id")
    system = build_system(mems, tasks.summary_for_prompt(db), projects,
                          datetime.now(TZ).strftime("%Y-%m-%d (%A)"))
    tier = tier if tier in ("fast", "smart") else choose_tier(text)

    res, call_id = await router.complete(system=system, messages=history, tier=tier, purpose=f"chat:{conv_id}")
    clean, new_mems, new_tasks = extract_markers(res.text)
    if not clean:
        clean = "(Boş yanıt döndü.)"
    asst = add_message(db, conv_id, "assistant", clean, model=f"{res.provider}:{res.model}", llm_call_id=call_id)

    saved_mems, created_tasks = [], []
    for kind, content in new_mems:
        mid = memory.add(db, content, kind=kind, source=f"chat:{conv_id}", confidence=0.7)
        saved_mems.append({"id": mid, "kind": kind, "content": content})
    slugs = {p["slug"]: p for p in db.query("SELECT id, slug FROM projects")}
    for prio, slug, title in new_tasks:
        proj = slugs.get(slug)
        t = tasks.create(db, title, kind="manual", project_id=proj["id"] if proj else None, priority=prio,
                         origin="chat", dedupe_key=f"chat:{title.lower()[:100]}")
        created_tasks.append({"id": t["id"], "title": t["title"], "deduplicated": bool(t.get("deduplicated"))})
    if saved_mems or created_tasks:
        log_activity(db, "chat_actions", f"Sohbetten {len(saved_mems)} hafıza, {len(created_tasks)} görev",
                     ref=f"conversation:{conv_id}")
    return {
        "conversation_id": conv_id,
        "user_message": user_msg,
        "assistant_message": asst,
        "tier": tier,
        "memories_saved": saved_mems,
        "tasks_created": created_tasks,
        "usage": {"input_tokens": res.input_tokens, "output_tokens": res.output_tokens},
    }
