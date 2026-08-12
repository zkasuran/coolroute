"""Proves the reasoning model does real tool calling through the configured
OpenAI-compatible endpoint. Two round trips:

  A. a prompt that should BUY A TOOL (a heat question needing data)
  B. a prompt that should ANSWER FREE (no tool needed)

Run:  PYTHONPATH=src python scripts/prove_gateway.py
Writes a transcript to artifacts/gateway-proof.txt. Uses the mock FortyGuard
backend so no FortyGuard key is needed to exercise the loop.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coolroute.agent import CoolRouteAgent  # noqa: E402
from coolroute.config import load_settings  # noqa: E402
from coolroute.fortyguard import get_client  # noqa: E402
from coolroute.llm import build_llm  # noqa: E402
from coolroute.tools import ToolRegistry, tool_schemas  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "gateway-proof.txt"


def main() -> int:
    s = load_settings()
    if not s.has_llm:
        print("No reasoning model configured; cannot prove the gateway.", file=sys.stderr)
        return 2

    llm = build_llm(s)
    lines: list[str] = []

    def log(msg: str) -> None:
        print(msg)
        lines.append(msg)

    log("== Case A: prompt that should buy a tool ==")
    agent = CoolRouteAgent(llm, s.openai_model, ToolRegistry(get_client(s)))
    q = ("When is the coolest 2-hour window to work outdoors in central Delhi "
         "(lat 28.61, lon 77.21) on 2024-07-15? Consider candidate start hours 6, 9, 12, 15, 18.")
    res = agent.run(q)
    tools_used = [x["tool"] for x in res.steps]
    log(f"tools_used: {tools_used}")
    log(f"answer:\n{res.final_text}\n")
    a_ok = len(tools_used) > 0

    log("== Case B: prompt that should answer free ==")
    resp = llm.chat.completions.create(
        model=s.openai_model,
        messages=[{"role": "user", "content": "Reply with exactly one word: pong"}],
        tools=tool_schemas(), tool_choice="auto",
    )
    msg = resp.choices[0].message
    free_tool_calls = getattr(msg, "tool_calls", None)
    log(f"tool_calls: {bool(free_tool_calls)}")
    log(f"answer: {msg.content!r}\n")
    b_ok = not free_tool_calls and bool(msg.content)

    verdict = "PASS" if (a_ok and b_ok) else "FAIL"
    log(f"== verdict: {verdict} (bought_tool={a_ok}, answered_free={b_ok}) ==")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {OUT}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
