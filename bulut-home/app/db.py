"""SQLite erişimi ve şema. WAL modu: tek yazar + eşzamanlı okuyucular, 8 GB RAM için yeterli."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    user_agent TEXT
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY,
    ip TEXT NOT NULL,
    at TEXT NOT NULL,
    success INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
    content TEXT NOT NULL,
    model TEXT,
    llm_call_id INTEGER REFERENCES llm_calls(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    purpose TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL,              -- NULL = fiyat bilinmiyor
    cost_known INTEGER NOT NULL DEFAULT 1,
    ok INTEGER NOT NULL,
    error TEXT,
    latency_ms INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON llm_calls(created_at);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'fact',      -- fact | preference | goal | decision | project | date
    content TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    source TEXT NOT NULL,                   -- 'user', 'chat:<conv_id>', 'task:<id>' ...
    confidence REAL NOT NULL DEFAULT 0.8,
    pinned INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_used_at TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, content='memories', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE OF content ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES ('delete', old.id, old.content);
    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'llm',          -- çalıştırıcı türü
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    parent_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    priority INTEGER NOT NULL DEFAULT 3,       -- 1 en yüksek, 5 en düşük
    origin TEXT NOT NULL DEFAULT 'board',      -- chat | goal | board | proposed
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','waiting_approval','running','done','failed','cancelled')),
    dedupe_key TEXT,
    estimated_cost_usd REAL,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_run_at TEXT,
    locked_by TEXT,
    locked_at TEXT,
    last_run_at TEXT,
    last_error TEXT,
    output TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);
-- Aynı işin iki kez kuyruğa girmesini engelle (aktif durumlar için)
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_dedupe ON tasks(dedupe_key)
    WHERE dedupe_key IS NOT NULL AND status IN ('pending','waiting_approval','running');
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority, id);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY,
    action TEXT NOT NULL,          -- spend_money | delete_data | account_change | live_change | external_irreversible
    summary TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','executed','expired')),
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT,
    executed_at TEXT
);

CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    detail TEXT,
    ref TEXT,
    level TEXT NOT NULL DEFAULT 'info',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity(created_at);
"""

DEFAULT_PROJECTS = [
    ("yan-daire", "Yan Daire", "Unity ile birinci şahıs psikolojik korku oyunu."),
    ("magaranin-disi", "Mağaranın Dışı", "Türkçe film ve dizi analizi YouTube kanalı."),
    ("gelir", "İş ve Gelir", "Freelance fırsatlar, teklifler ve gelir artırma."),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Her iş parçacığı için ayrı bağlantı; yazmalar tek kilit altında."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        self._local = threading.local()
        self.write_lock = threading.RLock()

    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA busy_timeout=30000")
            self._local.conn = c
        return c

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self.write_lock:
            c = self.conn()
            try:
                c.execute("BEGIN IMMEDIATE")
                yield c
                c.execute("COMMIT")
            except BaseException:
                c.execute("ROLLBACK")
                raise

    def query(self, sql: str, params: tuple | dict = ()) -> list[dict]:
        return [dict(r) for r in self.conn().execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | dict = ()) -> dict | None:
        r = self.conn().execute(sql, params).fetchone()
        return dict(r) if r else None

    def init(self) -> None:
        c = self.conn()
        c.executescript(SCHEMA)
        with self.tx() as t:
            t.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
            ts = now_iso()
            for slug, name, desc in DEFAULT_PROJECTS:
                t.execute(
                    "INSERT OR IGNORE INTO projects(slug,name,description,created_at,updated_at) VALUES (?,?,?,?,?)",
                    (slug, name, desc, ts, ts),
                )
            # Önceki çalışmada kilitli kalmış görevleri serbest bırak (çökme sonrası kurtarma)
            t.execute(
                "UPDATE tasks SET status='pending', locked_by=NULL, locked_at=NULL, updated_at=? WHERE status='running'",
                (ts,),
            )

    def backup(self, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(str(dest))
        try:
            self.conn().backup(target)
        finally:
            target.close()


def log_activity(db: Database, kind: str, summary: str, detail: str | None = None,
                 ref: str | None = None, level: str = "info") -> None:
    with db.tx() as t:
        t.execute(
            "INSERT INTO activity(kind,summary,detail,ref,level,created_at) VALUES (?,?,?,?,?,?)",
            (kind, summary, detail, ref, level, now_iso()),
        )
