"""The Cool Route Planner agent: an LLM that plans heat-aware routes and
schedules by calling the FortyGuard tools and explaining the result.

The LLM client is injected, so the loop runs against the live reasoning model in
production and against a scripted fake in tests (no network needed to prove the
tool-calling loop works).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .tools import ToolRegistry

SYSTEM_PROMPT = """\
You are Cool Route Planner, a heat-aware assistant for people who work, ride or \
walk outdoors in hot cities. You help them pick the coolest walking route or the \
coolest time-of-day window for an outdoor task.

Rules:
- Ground every number in the tools. Never invent a temperature; call a tool.
- The data is hyperlocal 2m-above-ground temperature, not a generic city forecast. \
Explain choices in terms of feels-like (heat index), wet-bulb and shade.
- Lead with a clear recommendation, then a short why, then the heat-risk band and \
one practical safety note (hydration, breaks) when the band is caution or worse.
- If a tool result is tagged "source": "mock", say the figures are from mock data.
- Keep it concise and plain. No marketing language."""


@dataclass
class AgentResult:
    final_text: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)


class CoolRouteAgent:
    def __init__(self, llm: Any, model: str, tools: ToolRegistry, max_steps: int = 6):
        self.llm = llm
        self.model = model
        self.tools = tools
        self.max_steps = max_steps

    def run(self, question: str, context: str | None = None) -> AgentResult:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": question})
        steps: list[dict[str, Any]] = []

        for _ in range(self.max_steps):
            resp = self.llm.chat.completions.create(
                model=self.model, messages=messages,
                tools=self.tools.schemas(), tool_choice="auto",
            )
            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                final = msg.content or ""
                messages.append({"role": "assistant", "content": final})
                return AgentResult(final_text=final, steps=steps, messages=messages)

            messages.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                name = tc.function.name
                args: dict[str, Any] = {}
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result = self.tools.dispatch(name, args)
                except Exception as exc:  # surface tool errors back to the model
                    result = {"error": True, "message": str(exc)}
                steps.append({"tool": name, "args": args, "result": result})
                messages.append({
                    "role": "tool", "tool_call_id": tc.id, "name": name,
                    "content": json.dumps(result),
                })

        # Ran out of steps: ask for a final answer with no more tools.
        resp = self.llm.chat.completions.create(model=self.model, messages=messages)
        final = resp.choices[0].message.content or ""
        return AgentResult(final_text=final, steps=steps, messages=messages)
