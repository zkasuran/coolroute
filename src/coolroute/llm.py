"""Reasoning-model client factory.

A top-tier OpenAI model reached over an OpenAI-compatible endpoint. Host, key and
model id all come from the environment (see .env.example); nothing is hard-coded.
"""
from __future__ import annotations

from typing import Any

from .config import Settings, load_settings


def build_llm(settings: Settings | None = None) -> Any:
    """Return an OpenAI-compatible client. Raises if no key is configured."""
    from openai import OpenAI

    settings = settings or load_settings()
    if not settings.has_llm:
        raise RuntimeError(
            "No reasoning model configured. Set OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL in .env."
        )
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
