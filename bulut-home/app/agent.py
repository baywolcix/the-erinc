"""Araç kullanan model döngüsü (manuel döngü: onay kapısı ve kayıt bizim kodumuzda)."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import tools as T
from .llm.providers import LLMResult
from .llm.router import LLMRouter, Route

MAX_STEPS = 6            # bir yanıt için en fazla model çağrısı
MAX_TOOL_CALLS = 12      # bir yanıt için en fazla araç çağrısı


@dataclass
class AgentResult:
    text: str
    last: LLMResult
    llm_call_ids: list[int] = field(default_factory=list)
    tool_events: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    stopped_reason: str | None = None


async def run(router: LLMRouter, ctx: T.ToolContext, *, system: str, messages: list[dict], tier: str,
              purpose: str, allowed_tools: list[str], max_tokens: int | None = None) -> AgentResult:
    specs = T.specs(allowed_tools, ctx.web)
    allowed = [s["name"] for s in specs]
    convo = list(messages)
    pinned: Route | None = None
    ids: list[int] = []
    tin = tout = calls = 0
    res: LLMResult | None = None
    stopped = None
    for step in range(MAX_STEPS):
        res, call_id = await router.complete(system=system, messages=convo, tier=tier, purpose=purpose,
                                             max_tokens=max_tokens, tools=specs or None, route=pinned)
        ids.append(call_id)
        tin += res.input_tokens
        tout += res.output_tokens
        if pinned is None and res.extra.get("route"):
            pinned = Route.parse(res.extra["route"])  # döngü boyunca aynı model (düşünme blokları modele bağlı)
        uses = res.tool_uses
        if res.stop_reason != "tool_use" or not uses:
            break
        convo.append({"role": "assistant", "content": res.content})
        results = []
        for u in uses:
            calls += 1
            if calls > MAX_TOOL_CALLS:
                out, err = "HATA: bu yanıt için araç çağrısı sınırı doldu; elindeki bilgiyle yanıtla.", True
            else:
                out, err = await T.run_tool(ctx, u["name"], u.get("input"), allowed, llm_call_id=call_id)
            block = {"type": "tool_result", "tool_use_id": u["id"], "content": out}
            if err:
                block["is_error"] = True
            results.append(block)
        convo.append({"role": "user", "content": results})  # tüm sonuçlar tek mesajda
    else:
        stopped = "max_steps"
    text = (res.text if res else "").strip()
    if stopped == "max_steps":
        text = (text + "\n\n" if text else "") + "(Adım sınırına ulaştım; iş yarım kalmış olabilir.)"
    elif res is not None and res.stop_reason == "max_tokens":
        text = (text + "\n\n" if text else "") + "(Yanıt uzunluk sınırında kesildi.)"
    return AgentResult(text=text, last=res, llm_call_ids=ids, tool_events=ctx.events, input_tokens=tin,
                       output_tokens=tout, stopped_reason=stopped)
