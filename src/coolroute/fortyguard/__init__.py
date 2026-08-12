"""FortyGuard adapter package. `get_client()` returns the mock or live backend
based on config, so a one-line env change swaps the whole data source.
"""
from __future__ import annotations

from ..config import Settings, load_settings
from .base import FortyGuardClient, FortyGuardError
from .live import LiveFortyGuardClient
from .mock import MockFortyGuardClient

__all__ = [
    "FortyGuardClient", "FortyGuardError",
    "MockFortyGuardClient", "LiveFortyGuardClient", "get_client",
]


def get_client(settings: Settings | None = None) -> FortyGuardClient:
    settings = settings or load_settings()
    if settings.fortyguard_backend == "live":
        return LiveFortyGuardClient(
            api_key=settings.fortyguard_api_key,
            base_url=settings.fortyguard_base_url,
        )
    return MockFortyGuardClient()
