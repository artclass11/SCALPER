"""Loopback-only Ollama parser; model output is validated as data."""

from __future__ import annotations

import json
import os
from urllib.parse import urlparse

import httpx

from scalper.schemas import StrategySpec


class LocalModelError(RuntimeError):
    pass


def _local_base_url() -> str:
    value = os.getenv("SCALPER_OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise LocalModelError("The Ollama endpoint must be an HTTP loopback URL for privacy.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LocalModelError("The Ollama URL must not contain credentials, query strings or fragments.")
    return value


async def parse_with_ollama(prompt: str) -> StrategySpec:
    model = os.getenv("SCALPER_OLLAMA_MODEL", "").strip()
    if not model or len(model) > 120:
        raise LocalModelError("Set SCALPER_OLLAMA_MODEL to an installed local model name.")
    base_url = _local_base_url()
    body = {
        "model": model,
        "stream": False,
        "format": StrategySpec.model_json_schema(),
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": (
                "Convert the request to one JSON object matching the schema. Only ema_crossover is supported. "
                "Never return code, credentials, explanations or extra fields. Use SPY and 1Day if absent. "
                "Set fast_ema below slow_ema."
            )},
            {"role": "user", "content": prompt[:500]},
        ],
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=2.0), follow_redirects=False
        ) as client:
            response = await client.post(f"{base_url}/api/chat", json=body)
        response.raise_for_status()
        parsed = json.loads(response.json()["message"]["content"])
        return StrategySpec.model_validate(parsed)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise LocalModelError("Local model did not return a valid supported strategy.") from exc
