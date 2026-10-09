"""Alpaca adapter with fixed paper trading host and limit orders only."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from scalper.schemas import StrategySpec

PAPER_TRADING_URL = "https://paper-api.alpaca.markets"
MARKET_DATA_URL = "https://data.alpaca.markets"


class BrokerConfigurationError(RuntimeError):
    pass


class BrokerRequestError(RuntimeError):
    pass


class AlpacaPaperBroker:
    """No method in this adapter can target a live trading URL."""

    def __init__(self) -> None:
        self.key = os.getenv("SCALPER_ALPACA_PAPER_KEY", "").strip()
        self.secret = os.getenv("SCALPER_ALPACA_PAPER_SECRET", "").strip()
        if not self.key or not self.secret:
            raise BrokerConfigurationError("Alpaca paper credentials are not configured.")
        self.headers = {
            "APCA-API-KEY-ID": self.key,
            "APCA-API-SECRET-KEY": self.secret,
            "Accept": "application/json",
        }

    async def _json_request(
        self, *, base_url: str, method: str, path: str,
        params: dict | None = None, json_body: dict | None = None, not_found_is_none: bool = False,
    ) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=base_url, timeout=httpx.Timeout(10.0, connect=4.0), follow_redirects=False
            ) as client:
                response = await client.request(
                    method, path, headers=self.headers, params=params, json=json_body
                )
            if not_found_is_none and response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json() if response.content else {}
        except httpx.TimeoutException as exc:
            raise BrokerRequestError("Alpaca paper API request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise BrokerRequestError(f"Alpaca paper API returned HTTP {exc.response.status_code}.") from None
        except httpx.RequestError as exc:
            raise BrokerRequestError("Unable to reach the configured Alpaca API host.") from exc
        except ValueError as exc:
            raise BrokerRequestError("Alpaca returned an invalid JSON response.") from exc

    async def get_account(self) -> dict[str, Any]:
        data = await self._json_request(base_url=PAPER_TRADING_URL, method="GET", path="/v2/account")
        return {
            "status": str(data.get("status", "unknown")),
            "currency": str(data.get("currency", "USD")),
            "equity": float(data.get("equity", 0)),
            "last_equity": float(data.get("last_equity", 0)),
            "buying_power": float(data.get("buying_power", 0)),
            "trading_blocked": bool(data.get("trading_blocked", False)),
        }

    async def get_bars(self, spec: StrategySpec, limit: int = 100) -> list[dict[str, Any]]:
        if spec.timeframe not in {"1Min", "5Min", "15Min", "1Hour", "1Day"}:
            raise ValueError("Unsupported Alpaca timeframe.")
        if not 10 <= limit <= 1000:
            raise ValueError("Bar limit must be between 10 and 1000.")
        payload = await self._json_request(
            base_url=MARKET_DATA_URL, method="GET", path=f"/v2/stocks/{spec.symbol}/bars",
            params={"timeframe": spec.timeframe, "limit": limit, "feed": "iex"},
        )
        bars = payload.get("bars", []) if isinstance(payload, dict) else []
        if not isinstance(bars, list):
            raise BrokerRequestError("Alpaca returned an invalid bars payload.")
        return [
            {"timestamp": str(bar["t"]), "open": float(bar["o"]), "high": float(bar["h"]),
             "low": float(bar["l"]), "close": float(bar["c"]), "volume": float(bar.get("v", 0))}
            for bar in bars if all(key in bar for key in ("t", "o", "h", "l", "c"))
        ]

    async def get_position(self, symbol: str) -> dict[str, Any] | None:
        if not re.fullmatch(r"[A-Z0-9./_-]{1,20}", symbol):
            raise ValueError("Invalid symbol.")
        payload = await self._json_request(
            base_url=PAPER_TRADING_URL, method="GET", path=f"/v2/positions/{symbol}",
            not_found_is_none=True,
        )
        if payload is None:
            return None
        return {"symbol": str(payload.get("symbol", symbol)), "qty": float(payload.get("qty", 0)),
                "side": str(payload.get("side", "long")), "market_value": float(payload.get("market_value", 0))}

    async def submit_limit_order(
        self, *, symbol: str, side: str, quantity: float, limit_price: float, client_order_id: str
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Z0-9./_-]{1,20}", symbol):
            raise ValueError("Invalid symbol.")
        if side not in {"buy", "sell"} or quantity <= 0 or limit_price <= 0:
            raise ValueError("Invalid limit order values.")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{8,48}", client_order_id):
            raise ValueError("Invalid client order id.")
        payload = await self._json_request(
            base_url=PAPER_TRADING_URL, method="POST", path="/v2/orders",
            json_body={
                "symbol": symbol, "qty": format(quantity, ".6f").rstrip("0").rstrip("."),
                "side": side, "type": "limit", "time_in_force": "day",
                "limit_price": format(limit_price, ".4f").rstrip("0").rstrip("."),
                "client_order_id": client_order_id,
            },
        )
        return {
            "id": str(payload.get("id", "")),
            "client_order_id": str(payload.get("client_order_id", client_order_id)),
            "symbol": str(payload.get("symbol", symbol)), "side": str(payload.get("side", side)),
            "qty": str(payload.get("qty", quantity)), "limit_price": str(payload.get("limit_price", limit_price)),
            "status": str(payload.get("status", "unknown")),
        }
