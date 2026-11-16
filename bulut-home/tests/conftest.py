import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.llm.pricing import Price  # noqa: E402
from app.llm.providers import LLMResult, ProviderError  # noqa: E402
from app.main import create_app  # noqa: E402

H = {"x-bulut": "1"}


class FakeProvider:
    """YALNIZCA TEST: gerçek API çağrısı yapmayan sahte sağlayıcı."""

    def __init__(self, name="anthropic", replies=None, fail_times=0, price=Price(1.0, 5.0), fatal=False):
        self.name = name
        self.replies = list(replies or [])
        self.fail_times = fail_times
        self.fatal = fatal
        self._price = price
        self.calls = []

    def available(self):
        return True

    def price(self, model):
        return self._price

    async def complete(self, *, model, system, messages, max_tokens, effort, tools=None):
        """Yanıt str ise düz metin; dict ise {"tools": [(ad, girdi), ...], "text": "..."} araç çağrısı simüle eder."""
        import copy
        self.calls.append({"model": model, "system": system, "messages": copy.deepcopy(messages), "effort": effort,
                           "tools": [t["name"] for t in tools] if tools else []})
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ProviderError("simüle edilmiş hata", retryable=not self.fatal)
        r = self.replies.pop(0) if self.replies else "Tamam."
        if isinstance(r, dict):
            content = ([{"type": "text", "text": r["text"]}] if r.get("text") else [])
            for i, (name, inp) in enumerate(r.get("tools", [])):
                content.append({"type": "tool_use", "id": f"toolu_{len(self.calls)}_{i}", "name": name, "input": inp})
            return LLMResult(text=r.get("text", ""), provider=self.name, model=model, input_tokens=1000, output_tokens=200,
                             stop_reason="tool_use" if r.get("tools") else "end_turn", content=content)
        return LLMResult(text=r, provider=self.name, model=model, input_tokens=1000, output_tokens=200,
                         stop_reason="end_turn", content=[{"type": "text", "text": r}])


def make_settings(tmp_path, **over):
    base = dict(
        data_dir=tmp_path, secret_key="test-secret", cookie_secure=False,
        anthropic_api_key="", compat_api_key="", compat_base_url="", compat_model="",
        compat_price_in=None, compat_price_out=None,
        model_fast="anthropic:claude-haiku-5-5", model_smart="anthropic:claude-sonnet-5-5",
        model_fallbacks=[], monthly_budget_try=400.0, usd_try_rate=40.0, worker_enabled=False,
    )
    base.update(over)
    return Settings(**base)


@pytest.fixture
def fake():
    return FakeProvider()


@pytest.fixture
def make_client(tmp_path):
    def _make(providers=None, **over):
        s = make_settings(tmp_path, **over)
        app = create_app(s, providers=providers if providers is not None else {"anthropic": FakeProvider()}, start_worker=False)
        return TestClient(app), app
    return _make


@pytest.fixture
def client(make_client, fake):
    c, app = make_client({"anthropic": fake})
    with c:
        token = (Path(app.state.bulut.settings.data_dir) / ".setup_token").read_text().strip()
        r = c.post("/api/auth/setup", json={"username": "umut", "password": "cok-gizli-parola", "setup_token": token}, headers=H)
        assert r.status_code == 200, r.text
        c.app_state = app.state.bulut
        c.fake = fake
        yield c


@pytest.fixture(autouse=True)
def _reset_notify():
    from app import notify
    notify.configure(notify.NotifyConfig())
    yield
    notify.configure(notify.NotifyConfig())
