"""Environment-backed configuration helpers."""

from __future__ import annotations

import os
from pathlib import Path


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def database_path() -> Path:
    configured = os.getenv("SCALPER_DB_PATH", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".scalper" / "scalper.sqlite3"


def allowed_origins() -> list[str]:
    return [value.strip() for value in os.getenv("SCALPER_ALLOWED_ORIGINS", "").split(",") if value.strip()]


def api_token() -> str:
    return os.getenv("SCALPER_API_TOKEN", "").strip()


def alpaca_paper_configured() -> bool:
    return bool(
        os.getenv("SCALPER_ALPACA_PAPER_KEY", "").strip()
        and os.getenv("SCALPER_ALPACA_PAPER_SECRET", "").strip()
    )
