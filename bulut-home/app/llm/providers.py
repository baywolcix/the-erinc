"""Sağlayıcı bağımsız LLM katmanı.

- AnthropicProvider: resmi `anthropic` SDK'sı.
- OpenAICompatProvider: OpenAI uyumlu /chat/completions sunan herhangi bir sağlayıcı
  (DeepSeek, OpenRouter, Groq, OpenAI ...). SDK'nın zaten getirdiği httpx2 kullanılır.
"""
from __future__ import annotations

import json
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
    # Anthropic biçiminde içerik blokları (text / tool_use / thinking ...). Araç döngüsünde
    # asistan mesajı olarak AYNEN geri gönderilir (düşünme blokları değiştirilmemeli).
    content: list[dict] = field(default_factory=list)

    @property
    def tool_uses(self) -> list[dict]:
        return [b for b in self.content if b.get("type") == "tool_use"]


class ProviderError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class Provider(Protocol):
    name: str

    def available(self) -> bool: ...
    def price(self, model: str) -> Price | None: ...
    async def complete(self, *, model: str, system: str, messages: list[dict],
                       max_tokens: int, effort: str | None, tools: list[dict] | None = None) -> LLMResult: ...


# Sunucu tarafı reddetme yedeği: model güvenlik sınıflandırıcısı yüzünden reddederse aynı istek
# bu modelde yeniden çalışır. Bütçe ön kontrolü öngörülebilir olsun diye "default" yerine sabit model.
REFUSAL_FALLBACK = {
    "claude-sonnet-5-5": "claude-sonnet-5",
    "claude-opus-5-5": "claude-opus-4-8",
}


class AnthropicProvider:
    name = "anthropic"

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

    async def complete(self, *, model, system, messages, max_tokens, effort, tools=None) -> LLMResult:
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
        if tools:
            kwargs["tools"] = tools
        try:
            if model in REFUSAL_FALLBACK:
                resp = await client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks=[{"model": REFUSAL_FALLBACK[model]}], **kwargs)
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
        iterations = []
        for it in (getattr(u, "iterations", None) or []):
            iterations.append({
                "type": getattr(it, "type", None), "model": getattr(it, "model", None) or model,
                "input_tokens": getattr(it, "input_tokens", 0) or 0, "output_tokens": getattr(it, "output_tokens", 0) or 0,
                "cache_read_tokens": getattr(it, "cache_read_input_tokens", 0) or 0,
                "cache_write_tokens": getattr(it, "cache_creation_input_tokens", 0) or 0,
            })
        return LLMResult(
            text=text,
            provider=self.name,
            model=resp.model or model,
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            stop_reason=resp.stop_reason,
            extra={"iterations": iterations} if iterations else {},
            content=[b.model_dump(mode="json", exclude_none=True) for b in resp.content],
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

    async def complete(self, *, model, system, messages, max_tokens, effort, tools=None) -> LLMResult:
        import httpx2

        model = self.resolve_model(model)
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}] + to_openai_messages(messages),
        }
        if tools:
            body["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t.get("description", ""), "parameters": t["input_schema"]}} for t in tools]
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
        msg = choice.get("message") or {}
        usage = data.get("usage") or {}
        text = msg.get("content") or ""
        content: list[dict] = [{"type": "text", "text": text}] if text else []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_invalid_json": fn.get("arguments")}
            content.append({"type": "tool_use", "id": tc.get("id") or f"call_{len(content)}", "name": fn.get("name"), "input": args})
        finish = choice.get("finish_reason")
        return LLMResult(
            text=text,
            provider=self.name,
            model=data.get("model") or model,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            stop_reason="tool_use" if finish == "tool_calls" or any(b["type"] == "tool_use" for b in content) else finish,
            content=content,
        )


def to_openai_messages(messages: list[dict]) -> list[dict]:
    """Anthropic biçimli mesajları (tool_use / tool_result blokları dahil) OpenAI biçimine çevirir."""
    out: list[dict] = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            out.append({"role": m["role"], "content": c})
            continue
        if m["role"] == "assistant":
            text = "".join(b.get("text", "") for b in c if b.get("type") == "text")
            calls = [{"id": b["id"], "type": "function",
                      "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False)}}
                     for b in c if b.get("type") == "tool_use"]
            msg: dict = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        else:
            texts = []
            for b in c:
                if b.get("type") == "tool_result":
                    rc = b.get("content")
                    if isinstance(rc, list):
                        rc = "".join(x.get("text", "") for x in rc)
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": str(rc)})
                elif b.get("type") == "text":
                    texts.append(b["text"])
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
    return out
