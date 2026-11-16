"""Oturum 2 denetiminde bulunan sorunların regresyon testleri."""
import asyncio

import pytest

from app import approvals
from app.db import Database, log_activity
from app.llm.pricing import ANTHROPIC_PRICES, cost_usd, worst_case_usd
from app.llm.providers import LLMResult
from app.llm.router import BudgetError, LLMRouter
from conftest import FakeProvider, make_settings


@pytest.mark.no_llm
def test_nested_transactions_use_savepoints(tmp_path):
    db = Database(tmp_path / "x.db"); db.init()
    with db.tx() as t:
        t.execute("INSERT INTO activity(kind,summary,created_at) VALUES ('a','dış','x')")
        log_activity(db, "b", "iç")  # önceden "cannot start a transaction within a transaction" verirdi
    assert db.one("SELECT COUNT(*) AS n FROM activity WHERE kind IN ('a','b')")["n"] == 2
    with pytest.raises(RuntimeError):
        with db.tx() as t:
            t.execute("INSERT INTO activity(kind,summary,created_at) VALUES ('c','geri alınacak','x')")
            raise RuntimeError
    assert db.one("SELECT COUNT(*) AS n FROM activity WHERE kind='c'")["n"] == 0


@pytest.mark.no_llm
def test_inner_rollback_keeps_outer(tmp_path):
    db = Database(tmp_path / "x.db"); db.init()
    with db.tx() as t:
        t.execute("INSERT INTO activity(kind,summary,created_at) VALUES ('dis','x','x')")
        try:
            with db.tx() as t2:
                t2.execute("INSERT INTO activity(kind,summary,created_at) VALUES ('ic','x','x')")
                raise ValueError
        except ValueError:
            pass
    kinds = {r["kind"] for r in db.query("SELECT kind FROM activity")}
    assert "dis" in kinds and "ic" not in kinds


@pytest.mark.no_llm
def test_haiku_long_prompt_tier():
    p = ANTHROPIC_PRICES["claude-haiku-5-5"]
    assert cost_usd(p, 50_000, 0) == pytest.approx(50_000 * 0.10 / 1e6)
    assert cost_usd(p, 150_000, 0) == pytest.approx(150_000 * 0.50 / 1e6)


@pytest.mark.no_llm
def test_worst_case_counts_cache_write_premium():
    p = ANTHROPIC_PRICES["claude-sonnet-5-5"]
    # 1M giriş: önbelleğe yazma 1.25x → 2.5 USD, + 0 çıktı
    assert worst_case_usd(p, 1_000_000, 0) == pytest.approx(2.5)


def _router(tmp_path, providers, **over):
    s = make_settings(tmp_path, **over)
    db = Database(s.db_path); db.init()
    return LLMRouter(db, s, providers), db


@pytest.mark.no_llm
def test_worst_case_includes_refusal_fallback(tmp_path):
    from app.llm.providers import AnthropicProvider
    r, _ = _router(tmp_path, {})
    prov = AnthropicProvider("x")
    single = worst_case_usd(ANTHROPIC_PRICES["claude-sonnet-5-5"], 1000, 1000)
    assert r._worst_usd(prov, "claude-sonnet-5-5", 1000, 1000) == pytest.approx(2 * single)
    assert r._worst_usd(prov, "claude-haiku-5-5", 1000, 1000) == pytest.approx(
        worst_case_usd(ANTHROPIC_PRICES["claude-haiku-5-5"], 1000, 1000))


@pytest.mark.no_llm
def test_cost_uses_each_iteration_model(tmp_path):
    from app.llm.providers import AnthropicProvider
    prov = AnthropicProvider("x")
    res = LLMResult(text="", provider="anthropic", model="claude-opus-4-8", input_tokens=0, output_tokens=0, extra={"iterations": [
        {"model": "claude-opus-5-5", "input_tokens": 1_000_000, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0},
        {"model": "claude-opus-4-8", "input_tokens": 1_000_000, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0},
    ]})
    assert LLMRouter._cost(prov, "claude-opus-5-5", res) == pytest.approx(4.0 + 5.0)


class SlowProvider(FakeProvider):
    async def complete(self, **kw):
        await asyncio.sleep(0.05)
        return await super().complete(**kw)


@pytest.mark.fake_llm
def test_concurrent_calls_cannot_jointly_exceed_budget(tmp_path):
    # Fiyat 1$/5$ per M, kur 40. Bir çağrının en kötü durumu: (≈60 giriş*1.25 + 4096*5)/1e6 USD ≈ 0.82 TL.
    # Bütçe 1.2 TL → aynı anda yalnızca bir çağrı sığar.
    p = SlowProvider()
    r, db = _router(tmp_path, {"anthropic": p}, monthly_budget_try=1.2)

    async def both():
        return await asyncio.gather(
            r.complete(system="s", messages=[{"role": "user", "content": "x"}]),
            r.complete(system="s", messages=[{"role": "user", "content": "y"}]),
            return_exceptions=True)
    out = asyncio.run(both())
    assert sum(isinstance(o, BudgetError) for o in out) == 1
    assert len(p.calls) == 1
    assert r._reserved_usd == 0.0  # ayrılan tutar bırakıldı


@pytest.mark.fake_llm
def test_reservation_released_on_provider_error(tmp_path):
    from app.llm.router import ProvidersFailed
    r, _ = _router(tmp_path, {"anthropic": FakeProvider(fail_times=1)})
    with pytest.raises(ProvidersFailed):
        asyncio.run(r.complete(system="s", messages=[{"role": "user", "content": "x"}]))
    assert r._reserved_usd == 0.0


@pytest.mark.no_llm
def test_failing_executor_is_reported(tmp_path):
    db = Database(tmp_path / "x.db"); db.init()

    @approvals.executor("_test_boom")
    def boom(db, payload):
        raise OSError("disk dolu")
    aid = approvals.request(db, "delete_data", "patlayan", {}, executor_name="_test_boom")
    res = approvals.decide(db, aid, True, "umut")
    assert "disk dolu" in res["result"]
    assert db.one("SELECT 1 AS x FROM activity WHERE kind='approval_failed'")
