"""Araç kullanımı ve agent döngüsü. Model FakeProvider (fake_llm): araç ÇAĞRILARI senaryoludur, araçların
kendisi (DB, onay, görev) gerçek koddur."""
import asyncio
import json

import pytest

from app import agent, tasks
from app import tools as T
from app.db import Database
from app.llm.router import LLMRouter
from conftest import H, FakeProvider, make_settings

pytestmark = pytest.mark.fake_llm


def _env(tmp_path, replies, **over):
    s = make_settings(tmp_path, **over)
    db = Database(s.db_path); db.init()
    p = FakeProvider(replies=replies)
    return db, LLMRouter(db, s, {"anthropic": p}), p


def test_chat_tool_loop_creates_task_and_memory(client):
    client.fake.replies = [
        {"text": "Bakıyorum.", "tools": [("search_memory", {"query": "Yan Daire"}),
                                         ("save_memory", {"content": "Yan Daire demosu Aralık sonu", "kind": "goal", "project_slug": "yan-daire"}),
                                         ("create_task", {"title": "Demo bölümünü test et", "kind": "manual", "priority": 2, "project_slug": "yan-daire"})]},
        "Kaydettim ve görevi ekledim.",
    ]
    r = client.post("/api/chat", json={"message": "Yan Daire demosunu Aralık sonuna yetiştirmeliyim, test görevini ekle"}, headers=H).json()
    assert r["assistant_message"]["content"] == "Kaydettim ve görevi ekledim."
    assert [e["name"] for e in r["tool_events"]] == ["search_memory", "save_memory", "create_task"]
    assert all(e["ok"] for e in r["tool_events"]) and r["usage"]["model_calls"] == 2
    # ikinci çağrıda: asistan tool_use içeriği + TEK kullanıcı mesajında 3 tool_result
    second = client.fake.calls[1]["messages"]
    assert second[-2]["role"] == "assistant" and [b["type"] for b in second[-2]["content"]] == ["text", "tool_use", "tool_use", "tool_use"]
    assert second[-1]["role"] == "user" and [b["type"] for b in second[-1]["content"]] == ["tool_result"] * 3
    assert "web_search" not in client.fake.calls[0]["tools"]  # arama yapılandırılmamış → araç sunulmaz
    t = client.get("/api/tasks").json()["tasks"][0]
    assert t["title"] == "Demo bölümünü test et" and t["project_slug"] == "yan-daire" and t["origin"] == "chat"
    mem = client.get("/api/memories", params={"q": "demosu"}).json()
    assert mem and mem[0]["source"].endswith(":tool")
    calls = client.get("/api/tool-calls").json()
    assert len(calls) == 3 and all(c["ok"] == 1 for c in calls)


def test_tool_errors_are_returned_to_model(client):
    client.fake.replies = [{"tools": [("create_task", {"title": "x", "kind": "hack"}), ("get_task", {"id": 999})]}, "Hata aldım."]
    r = client.post("/api/chat", json={"message": "görev ekle"}, headers=H).json()
    assert [e["ok"] for e in r["tool_events"]] == [False, False]
    results = client.fake.calls[1]["messages"][-1]["content"]
    assert all(b.get("is_error") for b in results) and "HATA" in results[0]["content"]


def test_delete_memory_tool_only_requests_approval(client):
    mid = client.post("/api/memories", json={"content": "Silinecek bilgi"}, headers=H).json()["id"]
    client.fake.replies = [{"tools": [("delete_memory", {"id": mid})]}, "Onay istedim."]
    client.post("/api/chat", json={"message": "o bilgiyi sil"}, headers=H)
    assert client.get("/api/memories").json()[0]["id"] == mid  # silinmedi
    ap = client.get("/api/approvals?status=pending").json()
    assert len(ap) == 1 and ap[0]["action"] == "delete_data"
    assert client.post(f"/api/approvals/{ap[0]['id']}/approve", headers=H).json()["status"] == "executed"
    assert client.get("/api/memories").json() == []


def test_unknown_or_disallowed_tool(tmp_path):
    db, router, _ = _env(tmp_path, [])
    ctx = T.ToolContext(db, "task:1")
    out, err = asyncio.run(T.run_tool(ctx, "create_task", {"title": "x", "kind": "manual"}, T.TASK_TOOLS))
    assert err and "aracı yok" in out
    assert tasks.list_tasks(db) == []
    out, err = asyncio.run(T.run_tool(ctx, "rm_rf", {}, T.CHAT_TOOLS))
    assert err


def test_invalid_json_input_rejected(tmp_path):
    db, _, _ = _env(tmp_path, [])
    out, err = asyncio.run(T.run_tool(T.ToolContext(db, "chat:1"), "save_memory", {"_invalid_json": "{"}, T.CHAT_TOOLS))
    assert err and "JSON" in out


def test_agent_step_limit(tmp_path):
    loop = [{"tools": [("list_tasks", {})]}] * 10
    db, router, p = _env(tmp_path, loop)
    res = asyncio.run(agent.run(router, T.ToolContext(db, "chat:1"), system="s", messages=[{"role": "user", "content": "x"}],
                                tier="fast", purpose="t", allowed_tools=T.CHAT_TOOLS))
    assert len(p.calls) == agent.MAX_STEPS and res.stopped_reason == "max_steps"
    assert "Adım sınırı" in res.text


def test_tool_call_cap(tmp_path):
    many = [("list_projects", {})] * 15
    db, router, p = _env(tmp_path, [{"tools": many}, "bitti"])
    res = asyncio.run(agent.run(router, T.ToolContext(db, "chat:1"), system="s", messages=[{"role": "user", "content": "x"}],
                                tier="fast", purpose="t", allowed_tools=T.CHAT_TOOLS))
    results = p.calls[1]["messages"][-1]["content"]
    assert len(results) == 15 and sum(1 for b in results if b.get("is_error")) == 15 - agent.MAX_TOOL_CALLS
    assert res.text == "bitti"


def test_agent_pins_route_across_steps(tmp_path):
    from app.llm.providers import ProviderError
    s = make_settings(tmp_path, model_fallbacks=["openai_compat:x"])
    db = Database(s.db_path); db.init()
    a = FakeProvider("anthropic", replies=[{"tools": [("list_projects", {})]}])
    b = FakeProvider("openai_compat", replies=["yedek"])
    router = LLMRouter(db, s, {"anthropic": a, "openai_compat": b})
    a.fail_times = 0
    orig = a.complete

    async def second_fails(**kw):
        if len(a.calls) >= 1:
            a.calls.append(kw)
            raise ProviderError("ikinci adımda hata")
        return await orig(**kw)
    a.complete = second_fails
    from app.llm.router import ProvidersFailed
    with pytest.raises(ProvidersFailed):
        asyncio.run(agent.run(router, T.ToolContext(db, "chat:1"), system="s", messages=[{"role": "user", "content": "x"}],
                              tier="fast", purpose="t", allowed_tools=T.CHAT_TOOLS))
    assert b.calls == []  # döngü ortasında başka sağlayıcıya (farklı biçim) atlamadı


def test_llm_task_uses_restricted_tools(tmp_path):
    db, router, p = _env(tmp_path, [{"tools": [("search_memory", {"query": "portföy"})]}, "Taslak hazır."])
    w = tasks.TaskWorker(db, router)
    tasks.create(db, "Bionluk teklif taslağı", kind="llm")
    out = asyncio.run(w.run_one())
    assert out["status"] == "done" and out["output"] == "Taslak hazır."
    offered = set(p.calls[0]["tools"])
    assert "create_task" not in offered and "update_task_status" not in offered and "delete_memory" not in offered
    assert db.one("SELECT context FROM tool_calls")["context"] == f"task:{out['id']}"
