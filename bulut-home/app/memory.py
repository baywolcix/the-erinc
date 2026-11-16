"""Uzun dönem hafıza: SQLite + FTS5 tam metin arama. Vektör veritabanı yok (RAM tasarrufu)."""
from __future__ import annotations

import re

from .db import Database, now_iso

KINDS = ("fact", "preference", "goal", "decision", "project", "date", "note")


def _fts_query(text: str) -> str:
    words = [w for w in re.findall(r"\w+", text.lower(), flags=re.UNICODE) if len(w) >= 3][:12]
    # Türkçe ekleri tolere etmek için önek araması
    return " OR ".join(f'"{w[:max(3, len(w) - 2)]}"*' for w in words)


def add(db: Database, content: str, kind: str = "fact", source: str = "user",
        confidence: float = 0.8, project_id: int | None = None, pinned: bool = False) -> int:
    content = content.strip()
    if not content:
        raise ValueError("Boş hafıza kaydı eklenemez.")
    if kind not in KINDS:
        kind = "note"
    with db.tx() as t:
        dup = t.execute("SELECT id FROM memories WHERE lower(content)=lower(?)", (content,)).fetchone()
        if dup:
            t.execute("UPDATE memories SET updated_at=?, confidence=MAX(confidence, ?) WHERE id=?",
                      (now_iso(), confidence, dup[0]))
            return dup[0]
        cur = t.execute(
            "INSERT INTO memories(kind,content,project_id,source,confidence,pinned,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (kind, content, project_id, source, max(0.0, min(1.0, confidence)), 1 if pinned else 0, now_iso(), now_iso()),
        )
        return cur.lastrowid


def update(db: Database, mem_id: int, **fields) -> bool:
    allowed = {k: v for k, v in fields.items() if k in ("content", "kind", "confidence", "pinned", "project_id") and v is not None}
    if not allowed:
        return False
    allowed["updated_at"] = now_iso()
    sets = ", ".join(f"{k}=?" for k in allowed)
    with db.tx() as t:
        cur = t.execute(f"UPDATE memories SET {sets} WHERE id=?", (*allowed.values(), mem_id))
        return cur.rowcount > 0


def delete(db: Database, mem_id: int) -> bool:
    """Kullanıcının kendi hafıza kaydını silmesi: kullanıcı arayüzden doğrudan istediği için onay gerektirmez."""
    with db.tx() as t:
        return t.execute("DELETE FROM memories WHERE id=?", (mem_id,)).rowcount > 0


def list_all(db: Database, q: str | None = None, limit: int = 200) -> list[dict]:
    if q:
        fq = _fts_query(q)
        if not fq:
            return []
        return db.query(
            "SELECT m.* FROM memories_fts f JOIN memories m ON m.id=f.rowid WHERE memories_fts MATCH ? "
            "ORDER BY bm25(memories_fts) LIMIT ?", (fq, limit))
    return db.query("SELECT * FROM memories ORDER BY pinned DESC, updated_at DESC LIMIT ?", (limit,))


def recall(db: Database, text: str, limit: int = 8) -> list[dict]:
    """Bir mesaj için ilgili hafızaları getir: sabitlenenler + FTS eşleşmeleri."""
    pinned = db.query("SELECT * FROM memories WHERE pinned=1 ORDER BY updated_at DESC LIMIT 10")
    found = list_all(db, text, limit) if text.strip() else []
    seen, out = set(), []
    for m in pinned + found:
        if m["id"] not in seen:
            seen.add(m["id"])
            out.append(m)
    if out:
        with db.tx() as t:
            t.executemany("UPDATE memories SET last_used_at=? WHERE id=?", [(now_iso(), m["id"]) for m in out])
    return out[: limit + 10]
