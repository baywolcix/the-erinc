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
