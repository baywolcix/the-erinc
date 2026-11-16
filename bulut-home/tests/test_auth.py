from pathlib import Path

from conftest import H


def test_setup_requires_token(make_client):
    c, app = make_client()
    with c:
        assert c.get("/api/auth/status").json()["needs_setup"] is True
        r = c.post("/api/auth/setup", json={"username": "a", "password": "uzun-parola-123", "setup_token": "yanlis"}, headers=H)
        assert r.status_code == 403


def test_protected_endpoints_need_login(make_client):
    c, _ = make_client()
    with c:
        for path in ("/api/tasks", "/api/memories", "/api/system", "/api/activity", "/api/conversations"):
            assert c.get(path).status_code == 401, path


def test_login_logout_and_bad_password(client):
    client.post("/api/auth/logout", headers=H)
    assert client.get("/api/tasks").status_code == 401
    assert client.post("/api/auth/login", json={"username": "umut", "password": "yanlis"}, headers=H).status_code == 401
    assert client.post("/api/auth/login", json={"username": "umut", "password": "cok-gizli-parola"}, headers=H).status_code == 200
    assert client.get("/api/tasks").status_code == 200


def test_setup_only_once(client):
    r = client.post("/api/auth/setup", json={"username": "x", "password": "baska-parola-1", "setup_token": "x"}, headers=H)
    assert r.status_code == 409


def test_csrf_header_required(client):
    r = client.post("/api/tasks", json={"title": "x"})
    assert r.status_code == 403


def test_login_rate_limit(client):
    client.post("/api/auth/logout", headers=H)
    for _ in range(8):
        client.post("/api/auth/login", json={"username": "umut", "password": "yanlis"}, headers=H)
    r = client.post("/api/auth/login", json={"username": "umut", "password": "cok-gizli-parola"}, headers=H)
    assert r.status_code == 429


def test_password_hashing():
    from app.auth import hash_password, verify_password
    h = hash_password("parola-12345")
    assert verify_password("parola-12345", h)
    assert not verify_password("parola-12346", h)
    assert "parola" not in h
