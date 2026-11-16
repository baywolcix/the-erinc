import asyncio

import pytest

from app.db import Database
from app.llm.pricing import cost_usd, Price, ANTHROPIC_PRICES
from app.llm.router import BudgetError, LLMRouter, ProvidersFailed, Route
from conftest import FakeProvider, make_settings


def _router(tmp_path, providers, **over):
    s = make_settings(tmp_path, **over)
    db = Database(s.db_path)
    db.init()
    return LLMRouter(db, s, providers), db


def run(coro):
    return asyncio.run(coro)


@pytest.mark.fake_llm
def test_fallback_on_provider_error(tmp_path):
    a = FakeProvider("anthropic", fail_times=5)
    b = FakeProvider("openai_compat", replies=["yedekten"])
    r, db = _router(tmp_path, {"anthropic": a, "openai_compat": b}, model_fallbacks=["openai_compat:deepseek-chat"])
    res, _ = run(r.complete(system="s", messages=[{"role": "user", "content": "x"}]))
    assert res.text == "yedekten"
    rows = db.query("SELECT provider, ok FROM llm_calls ORDER BY id")
    assert rows == [{"provider": "anthropic", "ok": 0}, {"provider": "openai_compat", "ok": 1}]


@pytest.mark.fake_llm
def test_all_fail(tmp_path):
    r, _ = _router(tmp_path, {"anthropic": FakeProvider(fail_times=9)})
    with pytest.raises(ProvidersFailed):
        run(r.complete(system="s", messages=[{"role": "user", "content": "x"}]))


@pytest.mark.fake_llm
def test_budget_blocks_when_exceeded(tmp_path):
    # 1 TL bütçe, kur 40: 1M çıktı token'ı 5 USD → çok pahalı
    r, db = _router(tmp_path, {"anthropic": FakeProvider()}, monthly_budget_try=1.0)
    with pytest.raises(BudgetError):
        run(r.complete(system="s", messages=[{"role": "user", "content": "x"}], max_tokens=100_000))
    assert db.query("SELECT * FROM llm_calls") == []  # hiç ücretli çağrı yapılmadı


@pytest.mark.fake_llm
def test_budget_blocks_without_rate(tmp_path):
    r, _ = _router(tmp_path, {"anthropic": FakeProvider()}, usd_try_rate=None)
    with pytest.raises(BudgetError):
        run(r.complete(system="s", messages=[{"role": "user", "content": "x"}]))
    assert r.budget_status()["blocked"] is True


@pytest.mark.fake_llm
def test_unknown_price_blocked(tmp_path):
    r, _ = _router(tmp_path, {"anthropic": FakeProvider(price=None)})
    with pytest.raises(BudgetError):
        run(r.complete(system="s", messages=[{"role": "user", "content": "x"}]))


@pytest.mark.fake_llm
def test_spend_accumulates(tmp_path):
    r, _ = _router(tmp_path, {"anthropic": FakeProvider()})
    run(r.complete(system="s", messages=[{"role": "user", "content": "x"}]))
    st = r.budget_status()
    # 1000 giriş * 1$/M + 200 çıkış * 5$/M = 0.002 USD
    assert st["spent_usd"] == pytest.approx(0.002)
    assert st["spent_try"] == pytest.approx(0.08)


@pytest.mark.fake_llm
def test_hourly_loop_guard(tmp_path, monkeypatch):
    import app.llm.router as rm
    monkeypatch.setattr(rm, "MAX_CALLS_PER_HOUR", 3)
    r, _ = _router(tmp_path, {"anthropic": FakeProvider()})
    for _ in range(3):
        run(r.complete(system="s", messages=[{"role": "user", "content": "x"}]))
    with pytest.raises(BudgetError):
        run(r.complete(system="s", messages=[{"role": "user", "content": "x"}]))


@pytest.mark.no_llm
def test_pricing():
    assert cost_usd(None, 1, 1) is None
    assert cost_usd(Price(2, 10), 1_000_000, 0) == pytest.approx(2.0)
    assert "claude-haiku-5-5" in ANTHROPIC_PRICES
    assert str(Route.parse("anthropic:claude-haiku-5-5")) == "anthropic:claude-haiku-5-5"


@pytest.mark.sdk_http
def test_openai_compat_provider_parses_response():
    import httpx2
    from app.llm.providers import OpenAICompatProvider, ProviderError

    def handler(request):
        assert request.headers["authorization"] == "Bearer k"
        return httpx2.Response(200, json={"model": "m", "choices": [{"message": {"content": "selam"}, "finish_reason": "stop"}],
                                          "usage": {"prompt_tokens": 10, "completion_tokens": 3}})
    p = OpenAICompatProvider("k", "https://example.invalid/v1", "m", 0.1, 0.2, transport=httpx2.MockTransport(handler))
    res = run(p.complete(model="default", system="s", messages=[{"role": "user", "content": "x"}], max_tokens=10, effort=None))
    assert (res.text, res.input_tokens, res.output_tokens) == ("selam", 10, 3)

    p2 = OpenAICompatProvider("k", "https://example.invalid/v1", "m", None, None,
                              transport=httpx2.MockTransport(lambda r: httpx2.Response(401, text="no")))
    with pytest.raises(ProviderError) as e:
        run(p2.complete(model="m", system="s", messages=[], max_tokens=10, effort=None))
    assert e.value.retryable is False
