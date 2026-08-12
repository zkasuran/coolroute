"""Configuration. Loads the lane .env with override so a stale process-level
OPENAI_BASE_URL cannot silently redirect the agent to the wrong endpoint.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# override=True: the file on disk wins over any variable already exported in the
# shell. Without this, a stale OPENAI_BASE_URL in the environment takes priority
# and the agent talks to the wrong host.
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=True)


@dataclass(frozen=True)
class Settings:
    fortyguard_backend: str
    fortyguard_base_url: str
    fortyguard_api_key: str
    openai_api_key: str
    openai_base_url: str
    openai_model: str

    @property
    def has_llm(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_live_key(self) -> bool:
        return bool(self.fortyguard_api_key)


def load_settings() -> Settings:
    return Settings(
        fortyguard_backend=os.getenv("FORTYGUARD_BACKEND", "mock").strip().lower(),
        fortyguard_base_url=os.getenv(
            "FORTYGUARD_BASE_URL", "https://api.fortyguard.com/v1"
        ).rstrip("/"),
        fortyguard_api_key=os.getenv("FORTYGUARD_API_KEY", "").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o").strip(),
    )
