from conftest import H, FakeProvider

import pytest as _pt

pytestmark = _pt.mark.fake_llm


def test_chat_persists_and_uses_history(client):
    client.fake.replies = ["Merhaba Umut.", "Az önce selam verdin."]
    r = client.post("/api/chat", json={"message": "Selam BULUT"}, headers=H)
    assert r.status_code == 200, r.text
    cid = r.json()["conversation_id"]
    assert r.json()["assistant_message"]["content"] == "Merhaba Umut."
    r2 = client.post("/api/chat", json={"message": "Ne dedim?", "conversation_id": cid}, headers=H)
    assert r2.status_code == 200
    last_call = client.fake.calls[-1]
    assert [m["role"] for m in last_call["messages"]] == ["user", "assistant", "user"]
    conv = client.get(f"/api/conversations/{cid}").json()
    assert [m["content"] for m in conv["messages"]] == ["Selam BULUT", "Merhaba Umut.", "Ne dedim?", "Az önce selam verdin."]
    # maliyet kaydı
    calls = client.app_state.db.query("SELECT * FROM llm_calls")
    assert len(calls) == 2 and all(c["ok"] == 1 and c["cost_usd"] > 0 for c in calls)


def test_markers_create_memory_and_task(client):
    client.fake.replies = ["Not aldım.\n[[HATIRLA:preference|Kısa yanıtları sever]]\n[[GOREV:2|yan-daire|Bölüm 2 kapı mekaniğini test et]]"]
    r = client.post("/api/chat", json={"message": "Kısa yanıt ver ve Yan Daire kapı testini listeye ekle"}, headers=H).json()
    assert r["assistant_message"]["content"] == "Not aldım."
    assert r["memories_saved"][0]["content"] == "Kısa yanıtları sever"
    assert r["tasks_created"][0]["title"] == "Bölüm 2 kapı mekaniğini test et"
    t = client.get(f"/api/tasks/{r['tasks_created'][0]['id']}").json()
    assert t["project_slug"] == "yan-daire" and t["origin"] == "chat" and t["priority"] == 2


def test_memory_is_recalled_into_system_prompt(client):
    client.post("/api/memories", json={"content": "Mağaranın Dışı kanalı haftada bir video yayınlar", "kind": "project"}, headers=H)
    client.post("/api/chat", json={"message": "Mağaranın kanalı için yayın sıklığı neydi?"}, headers=H)
    assert "haftada bir video" in client.fake.calls[-1]["system"]


def test_tier_selection(client):
    client.post("/api/chat", json={"message": "selam"}, headers=H)
    assert client.fake.calls[-1]["model"] == "claude-haiku-5-5"
    client.post("/api/chat", json={"message": "Bu haftanın gelir stratejisini detaylı analiz et"}, headers=H)
    assert client.fake.calls[-1]["model"] == "claude-sonnet-5-5"


def test_no_provider_returns_503(make_client):
    from pathlib import Path
    c, app = make_client(providers={})
    with c:
        token = (Path(app.state.bulut.settings.data_dir) / ".setup_token").read_text().strip()
        c.post("/api/auth/setup", json={"username": "u", "password": "uzun-parola-1", "setup_token": token}, headers=H)
        r = c.post("/api/chat", json={"message": "selam"}, headers=H)
        assert r.status_code == 503
        assert "yapılandırılmamış" in r.json()["detail"]
