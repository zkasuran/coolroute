"""Minimal demo web UI (FastAPI).

SECURITY: this server has no authentication by default. It only reads heat data
(mock or live) and performs no writes, so the blast radius is low, but do not
expose it publicly as-is. Set COOLROUTE_WEB_KEY in the environment to require an
`x-api-key` header on the planning endpoints. When it is unset the server logs a
warning and runs open, which is intended only for a local demo.

Run:  PYTHONPATH=src uvicorn web.app:app --reload
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from coolroute.config import load_settings
from coolroute.fortyguard import get_client
from coolroute.planner import evaluate_routes, find_coolest_hour
from coolroute.scenarios import SCENARIOS

log = logging.getLogger("coolroute.web")
DEMO_DATE = "2024-07-15"
_INDEX = (Path(__file__).parent / "index.html").read_text()

app = FastAPI(title="Cool Route Planner", version="0.1.0")


def _check_key(x_api_key: str | None) -> None:
    required = os.getenv("COOLROUTE_WEB_KEY", "").strip()
    if not required:
        log.warning("COOLROUTE_WEB_KEY is not set: planning endpoints are unauthenticated (demo mode).")
        return
    if x_api_key != required:
        raise HTTPException(status_code=401, detail="missing or invalid x-api-key header")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX


@app.get("/health")
def health() -> dict:
    s = load_settings()
    return {"backend": get_client(s).backend, "llm_configured": s.has_llm}


@app.post("/api/route")
def api_route(x_api_key: str | None = Header(default=None)) -> JSONResponse:
    _check_key(x_api_key)
    sc = SCENARIOS["abu-dhabi-route"]
    result = evaluate_routes(get_client(), sc["routes"], DEMO_DATE, sc["hour"])
    return JSONResponse(result)


@app.post("/api/time")
def api_time(x_api_key: str | None = Header(default=None)) -> JSONResponse:
    _check_key(x_api_key)
    sc = SCENARIOS["delhi-shift"]
    result = find_coolest_hour(get_client(), sc["latitude"], sc["longitude"], DEMO_DATE,
                               sc["candidate_hours"], sc["duration_hours"])
    return JSONResponse(result)


@app.post("/api/ask")
def api_ask(payload: dict, x_api_key: str | None = Header(default=None)) -> JSONResponse:
    _check_key(x_api_key)
    s = load_settings()
    if not s.has_llm:
        raise HTTPException(status_code=503, detail="no reasoning model configured")
    from coolroute.agent import CoolRouteAgent
    from coolroute.llm import build_llm
    from coolroute.tools import ToolRegistry

    agent = CoolRouteAgent(build_llm(s), s.openai_model, ToolRegistry(get_client(s)))
    result = agent.run(str(payload.get("question", "")), context=f"Use date {DEMO_DATE} unless told otherwise.")
    return JSONResponse({"answer": result.final_text, "tools": [x["tool"] for x in result.steps]})
