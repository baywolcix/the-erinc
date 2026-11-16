"""GERÇEK API testleri — ücretlidir. Yalnızca açıkça istendiğinde çalışır:

    BULUT_LIVE_TESTS=1 ANTHROPIC_API_KEY=... python -m pytest -m live tests/live

Her test tek, kısa bir çağrı yapar (Haiku 5.5, max_tokens küçük): tahmini maliyet < 0.01 USD.
"""
import asyncio
import os

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("BULUT_LIVE_TESTS") != "1", reason="Canlı API testleri kapalı (BULUT_LIVE_TESTS=1 değil)"),
]


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY yok")
def test_live_anthropic_haiku():
    from app.llm.providers import AnthropicProvider
    p = AnthropicProvider(os.environ["ANTHROPIC_API_KEY"])
    res = asyncio.run(p.complete(model="claude-haiku-5-5", system="Kısa yanıt ver.",
                                 messages=[{"role": "user", "content": "Sadece 'tamam' yaz."}], max_tokens=200, effort="low"))
    assert res.text.strip() and res.input_tokens > 0 and res.output_tokens > 0


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY yok")
def test_live_anthropic_tool_use():
    from app.llm.providers import AnthropicProvider
    p = AnthropicProvider(os.environ["ANTHROPIC_API_KEY"])
    tools = [{"name": "list_tasks", "description": "Görevleri listeler.",
              "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}}]
    res = asyncio.run(p.complete(model="claude-haiku-5-5", system="Görev sorulursa list_tasks aracını kullan.",
                                 messages=[{"role": "user", "content": "Açık görevlerim neler?"}], max_tokens=500,
                                 effort="low", tools=tools))
    assert res.stop_reason in ("tool_use", "end_turn")


@pytest.mark.skipif(not os.environ.get("OPENAI_COMPAT_API_KEY"), reason="OPENAI_COMPAT_API_KEY yok")
def test_live_openai_compat():
    from app.llm.providers import OpenAICompatProvider
    p = OpenAICompatProvider(os.environ["OPENAI_COMPAT_API_KEY"], os.environ["OPENAI_COMPAT_BASE_URL"],
                             os.environ["OPENAI_COMPAT_MODEL"], None, None)
    res = asyncio.run(p.complete(model="default", system="Kısa yanıt ver.",
                                 messages=[{"role": "user", "content": "Sadece 'tamam' yaz."}], max_tokens=20, effort=None))
    assert res.text.strip()
