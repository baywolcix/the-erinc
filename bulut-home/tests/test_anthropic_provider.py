"""AnthropicProvider'ın SDK ile kurduğu isteği sahte HTTP katmanıyla doğrular (ağ çağrısı yok)."""
import asyncio
import json

import httpx2
import pytest
from anthropic import DefaultAsyncHttpxClient

from app.llm.providers import AnthropicProvider, ProviderError

import pytest as _pt

pytestmark = _pt.mark.sdk_http


def _provider(handler):
    return AnthropicProvider("sk-test", http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)))


def _ok_body(model):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": model,
            "content": [{"type": "thinking", "thinking": "", "signature": "x"}, {"type": "text", "text": "Merhaba"}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 12, "output_tokens": 4, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}


def test_haiku_request_shape():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        seen["beta"] = req.headers.get("anthropic-beta")
        return httpx2.Response(200, json=_ok_body("claude-haiku-5-5"))

    res = asyncio.run(_provider(handler).complete(model="claude-haiku-5-5", system="sys",
                                                  messages=[{"role": "user", "content": "selam"}], max_tokens=100, effort="low"))
    assert res.text == "Merhaba" and res.input_tokens == 12 and res.output_tokens == 4
    b = seen["body"]
    assert b["model"] == "claude-haiku-5-5" and b["output_config"] == {"effort": "low"}
    assert "temperature" not in b and "thinking" not in b
    assert seen["beta"] is None


def test_sonnet_uses_server_side_fallback():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        seen["beta"] = req.headers.get("anthropic-beta")
        return httpx2.Response(200, json=_ok_body("claude-sonnet-5-5"))

    asyncio.run(_provider(handler).complete(model="claude-sonnet-5-5", system="s",
                                            messages=[{"role": "user", "content": "x"}], max_tokens=100, effort="medium"))
    assert seen["body"]["fallbacks"] == [{"model": "claude-sonnet-5"}]
    assert "server-side-fallback-2026-07-01" in seen["beta"]


def test_auth_error_not_retryable():
    p = _provider(lambda req: httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "bad"}}))
    with pytest.raises(ProviderError) as e:
        asyncio.run(p.complete(model="claude-haiku-5-5", system="s", messages=[{"role": "user", "content": "x"}], max_tokens=10, effort=None))
    assert e.value.retryable is False


def test_fallback_iterations_are_parsed():
    def handler(req):
        body = _ok_body("claude-sonnet-5")
        body["usage"]["iterations"] = [
            {"type": "message", "model": "claude-sonnet-5-5", "input_tokens": 100, "output_tokens": 10,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            {"type": "fallback_message", "model": "claude-sonnet-5", "input_tokens": 100, "output_tokens": 50,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        ]
        return httpx2.Response(200, json=body)
    res = asyncio.run(_provider(handler).complete(model="claude-sonnet-5-5", system="s",
                                                  messages=[{"role": "user", "content": "x"}], max_tokens=100, effort=None))
    its = res.extra["iterations"]
    assert [i["model"] for i in its] == ["claude-sonnet-5-5", "claude-sonnet-5"]


def test_tool_use_roundtrip_preserves_thinking_blocks():
    """Araç döngüsü: ilk yanıttaki thinking + tool_use blokları ikinci istekte AYNEN geri gönderilmeli."""
    from app import agent, tools as T
    from app.db import Database
    from app.llm.router import LLMRouter
    import tempfile
    from pathlib import Path
    from conftest import make_settings

    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        if len(bodies) == 1:
            return httpx2.Response(200, json={
                "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
                "content": [{"type": "thinking", "thinking": "", "signature": "SIG123"},
                            {"type": "tool_use", "id": "toolu_A", "name": "list_projects", "input": {}}],
                "stop_reason": "tool_use", "stop_sequence": None,
                "usage": {"input_tokens": 50, "output_tokens": 20}})
        return httpx2.Response(200, json=_ok_body("claude-haiku-5-5"))

    tmp = Path(tempfile.mkdtemp())
    s = make_settings(tmp)
    db = Database(s.db_path); db.init()
    router = LLMRouter(db, s, {"anthropic": _provider(handler)})
    res = asyncio.run(agent.run(router, T.ToolContext(db, "chat:1"), system="s", messages=[{"role": "user", "content": "projeler?"}],
                                tier="fast", purpose="t", allowed_tools=T.CHAT_TOOLS))
    assert res.text == "Merhaba"
    assert any(t["name"] == "list_projects" for t in bodies[0]["tools"])
    assert "tool_choice" not in bodies[0]  # 5.5 modellerinde zorlanmış araç seçimi 400 verir
    sent = bodies[1]["messages"]
    assert sent[1]["role"] == "assistant"
    assert sent[1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "SIG123"}
    assert sent[1]["content"][1]["type"] == "tool_use" and sent[1]["content"][1]["id"] == "toolu_A"
    assert sent[2]["content"][0]["type"] == "tool_result" and sent[2]["content"][0]["tool_use_id"] == "toolu_A"
    assert "Yan Daire" in sent[2]["content"][0]["content"]
