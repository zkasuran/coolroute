"""Command-line interface.

Run offline and deterministic by default (mock backend). `ask` and `--llm` use
the reasoning model if one is configured in .env.

  PYTHONPATH=src python -m coolroute demo
  PYTHONPATH=src python -m coolroute coolest-route
  PYTHONPATH=src python -m coolroute coolest-time
  PYTHONPATH=src python -m coolroute ask "When is the coolest hour to work in Delhi?"
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import load_settings
from .fortyguard import get_client
from .planner import evaluate_routes, find_coolest_hour
from .scenarios import SCENARIOS
from .tools import ToolRegistry

DEMO_DATE = "2024-07-15"  # a valid historical summer date; near-term within 12h works the same


def _print_route(result: dict) -> None:
    src = result["source"]
    best = result["coolest_route"]
    print(f"\nCoolest route at {result['hour']:02d}:00 ({src} data): {best['route']}")
    print(f"  {best['description']}")
    print(f"{'route':<22}{'feels-like':>12}{'max':>8}{'shade':>8}{'metres':>9}  risk")
    for r in result["ranked"]:
        if r.get("mean_feels_like_celsius") is None:
            print(f"{r['route']:<22}{'no readings available':>39}")
            continue
        print(f"{r['route']:<22}{r['mean_feels_like_celsius']:>11.1f}C"
              f"{r['max_feels_like_celsius']:>7.1f}{r['mean_shade_fraction']:>8.2f}"
              f"{r['length_m']:>9}  {r['heat_risk_band']}")


def _print_time(result: dict) -> None:
    src = result["source"]
    best = result["coolest"]
    print(f"\nCoolest window ({src} data): start {best['start_hour']:02d}:00 "
          f"for {best['window_hours']}h, feels-like {best['avg_feels_like_celsius']}C")
    print(f"{'start':>6}{'avg feels-like':>16}{'peak':>8}  risk")
    for r in result["ranked"]:
        print(f"{r['start_hour']:>4}:00{r['avg_feels_like_celsius']:>15.1f}C"
              f"{r['peak_feels_like_celsius']:>7.1f}  {r['heat_risk_band']}")


def cmd_route(client) -> None:
    sc = SCENARIOS["abu-dhabi-route"]
    _print_route(evaluate_routes(client, sc["routes"], DEMO_DATE, sc["hour"]))


def cmd_time(client) -> None:
    sc = SCENARIOS["delhi-shift"]
    _print_time(find_coolest_hour(client, sc["latitude"], sc["longitude"], DEMO_DATE,
                                  sc["candidate_hours"], sc["duration_hours"]))


def cmd_ask(question: str) -> int:
    settings = load_settings()
    if not settings.has_llm:
        print("No reasoning model configured. Set OPENAI_* in .env, or use the "
              "deterministic commands (demo / coolest-route / coolest-time).", file=sys.stderr)
        return 2
    from .agent import CoolRouteAgent
    from .llm import build_llm

    client = get_client(settings)
    agent = CoolRouteAgent(build_llm(settings), settings.openai_model, ToolRegistry(client))
    result = agent.run(question, context=f"Use date {DEMO_DATE} unless the user gives one.")
    print(result.final_text)
    if result.steps:
        print("\n[tools used]", ", ".join(s["tool"] for s in result.steps), file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coolroute", description="Heat-aware route and schedule planner.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="run both deterministic scenarios")
    sub.add_parser("coolest-route", help="rank demo routes by heat (deterministic)")
    sub.add_parser("coolest-time", help="rank demo time windows by heat (deterministic)")
    p_ask = sub.add_parser("ask", help="ask the agent in free text (needs a reasoning model)")
    p_ask.add_argument("question")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.cmd == "ask":
        return cmd_ask(args.question)

    client = get_client(settings)
    print(f"# FortyGuard backend: {client.backend}"
          + ("  (offline synthetic data, labelled 'mock')" if client.backend == "mock" else ""))
    if args.cmd in ("demo", "coolest-route"):
        cmd_route(client)
    if args.cmd in ("demo", "coolest-time"):
        cmd_time(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
