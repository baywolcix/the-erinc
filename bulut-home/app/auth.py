"""Tek sahipli kimlik doğrulama: scrypt parola özeti + sunucu tarafı oturum tablosu."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from .db import Database, now_iso

SESSION_DAYS = 30
LOGIN_WINDOW_MIN = 15
LOGIN_MAX_FAILS = 8

_N, _R, _P = 2**14, 8, 1  # ~16 MB bellek, ASUS için uygun


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(dk)))
        return hmac.compare_digest(calc.hex(), dk)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def has_owner(db: Database) -> bool:
    return db.one("SELECT 1 AS x FROM users LIMIT 1") is not None


def create_owner(db: Database, username: str, password: str) -> None:
    if len(password) < 10:
        raise ValueError("Parola en az 10 karakter olmalı.")
    with db.tx() as t:
        if t.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            raise ValueError("Sahip hesabı zaten var.")
        t.execute("INSERT INTO users(username,password_hash,created_at) VALUES (?,?,?)",
                  (username.strip(), hash_password(password), now_iso()))


def set_password(db: Database, username: str, password: str) -> None:
    if len(password) < 10:
        raise ValueError("Parola en az 10 karakter olmalı.")
    with db.tx() as t:
        cur = t.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(password), username))
        if cur.rowcount == 0:
            t.execute("INSERT INTO users(username,password_hash,created_at) VALUES (?,?,?)",
                      (username, hash_password(password), now_iso()))
        t.execute("DELETE FROM sessions")  # parola değişince tüm oturumlar düşer


def too_many_failures(db: Database, ip: str) -> bool:
    since = (datetime.now(timezone.utc) - timedelta(minutes=LOGIN_WINDOW_MIN)).isoformat(timespec="seconds")
    n = db.one("SELECT COUNT(*) AS n FROM login_attempts WHERE ip=? AND success=0 AND at>=?", (ip, since))["n"]
    return n >= LOGIN_MAX_FAILS


def login(db: Database, secret: str, username: str, password: str, ip: str, ua: str) -> str | None:
    user = db.one("SELECT * FROM users WHERE username=?", (username.strip(),))
    ok = bool(user) and verify_password(password, user["password_hash"])
    with db.tx() as t:
        t.execute("INSERT INTO login_attempts(ip,at,success) VALUES (?,?,?)", (ip, now_iso(), 1 if ok else 0))
        if not ok:
            return None
        token = secrets.token_urlsafe(32)
        exp = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
        t.execute("INSERT INTO sessions(token_hash,user_id,created_at,expires_at,user_agent) VALUES (?,?,?,?,?)",
                  (_token_hash(token, secret), user["id"], now_iso(), exp, ua[:200]))
        return token


def session_user(db: Database, secret: str, token: str | None) -> dict | None:
    if not token:
        return None
    row = db.one(
        "SELECT u.id, u.username, s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
        (_token_hash(token, secret),),
    )
    if not row or row["expires_at"] < now_iso():
        return None
    return {"id": row["id"], "username": row["username"]}


def logout(db: Database, secret: str, token: str | None) -> None:
    if token:
        with db.tx() as t:
            t.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token, secret),))
