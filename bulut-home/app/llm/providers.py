"""Sağlayıcı bağımsız LLM katmanı.

- AnthropicProvider: resmi `anthropic` SDK'sı.
- OpenAICompatProvider: OpenAI uyumlu /chat/completions sunan herhangi bir sağlayıcı
  (DeepSeek, OpenRouter, Groq, OpenAI ...). SDK'nın zaten getirdiği httpx2 kullanılır.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .pricing import ANTHROPIC_PRICES, Price


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    stop_reason: str | None = None
    extra: dict = field(default_factory=dict)


class ProviderError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class Provider(Protocol):
    name: str

    def available(self) -> bool: ...
    def price(self, model: str) -> Price | None: ...
    async def complete(self, *, model: str, system: str, messages: list[dict],
                       max_tokens: int, effort: str | None) -> LLMResult: ...


class AnthropicProvider:
    name = "anthropic"
    # Sunucu tarafı reddetme yedeği (refusal fallback) desteklenen modeller
    _FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"}

    def __init__(self, api_key: str, http_client=None):
        self._api_key = api_key
        self._client = None
        self._http_client = http_client  # testler için

    def available(self) -> bool:
        return bool(self._api_key)

    def price(self, model: str) -> Price | None:
        return ANTHROPIC_PRICES.get(model)

    def _get_client(self):
        if self._client is None:
            import anthropic
            # Yeniden denemeyi router yönetir; SDK'da 1 deneme yeterli.
            kw = {"http_client": self._http_client} if self._http_client is not None else {}
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key, max_retries=1, timeout=120.0, **kw)
        return self._client

    async def complete(self, *, model, system, messages, max_tokens, effort) -> LLMResult:
        import anthropic

        client = self._get_client()
        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            cache_control={"type": "ephemeral"},
        )
        if effort:
            kwargs["output_config"] = {"effort": effort}
        try:
            if model in self._FALLBACK_MODELS:
                resp = await client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
            else:
                resp = await client.messages.create(**kwargs)
        except anthropic.AuthenticationError as e:
            raise ProviderError(f"Anthropic kimlik doğrulama hatası: {e}", retryable=False) from e
        except anthropic.BadRequestError as e:
            raise ProviderError(f"Anthropic geçersiz istek: {e}", retryable=False) from e
        except anthropic.RateLimitError as e:
            raise ProviderError(f"Anthropic hız sınırı: {e}") from e
        except anthropic.APIStatusError as e:
            raise ProviderError(f"Anthropic API hatası {e.status_code}: {e}") from e
        except anthropic.APIConnectionError as e:
            raise ProviderError(f"Anthropic bağlantı hatası: {e}") from e

        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        if resp.stop_reason == "refusal":
            text = text or "Bu isteği model güvenlik politikası nedeniyle yanıtlamadı."
        u = resp.usage
        return LLMResult(
            text=text,
            provider=self.name,
            model=resp.model or model,
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            stop_reason=resp.stop_reason,
        )


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(self, api_key: str, base_url: str, default_model: str,
                 price_in: float | None, price_out: float | None, transport=None):
        self._api_key = api_key
        self._base_url = base_url
        self._default_model = default_model
        self._price = Price(price_in, price_out) if price_in is not None and price_out is not None else None
        self._transport = transport

    def available(self) -> bool:
        return bool(self._api_key and self._base_url and self._default_model)

    def resolve_model(self, model: str) -> str:
        return self._default_model if model in ("", "default") else model

    def price(self, model: str) -> Price | None:
        return self._price

    async def complete(self, *, model, system, messages, max_tokens, effort) -> LLMResult:
        import httpx2

        model = self.resolve_model(model)
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}] + messages,
        }
        try:
            async with httpx2.AsyncClient(timeout=120.0, transport=self._transport) as client:
                r = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                )
        except httpx2.HTTPError as e:
            raise ProviderError(f"{self._base_url} bağlantı hatası: {e}") from e
        if r.status_code >= 400:
            retryable = r.status_code in (408, 409, 429) or r.status_code >= 500
            raise ProviderError(f"OpenAI uyumlu API hatası {r.status_code}: {r.text[:300]}", retryable=retryable)
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage") or {}
        return LLMResult(
            text=(choice.get("message") or {}).get("content") or "",
            provider=self.name,
            model=data.get("model") or model,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            stop_reason=choice.get("finish_reason"),
        )
