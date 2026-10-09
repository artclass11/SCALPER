"""Alpaca adapter fixed to the paper trading host, with idempotent limit orders."""

from __future__ import annotations

import math
import os
import re
from typing import Any

import httpx
from pydantic import ValidationError

from scalper.schemas import Candle, StrategySpec

PAPER_TRADING_URL = "https://paper-api.alpaca.markets"
MARKET_DATA_URL = "https://data.alpaca.markets"
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
_ORDER_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,48}$")


class BrokerConfigurationError(RuntimeError):
    pass


class BrokerRequestError(RuntimeError):
    pass


class BrokerOrderConflict(BrokerRequestError):
    """The requested idempotency key already identifies a different order."""


def _number(value: Any, field: str, *, allow_negative: bool = False) -> float:
    if isinstance(value, bool):
        raise BrokerRequestError(f"Alpaca returned an invalid {field} value.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BrokerRequestError(f"Alpaca returned an invalid {field} value.") from exc
    if not math.isfinite(result) or (not allow_negative and result < 0):
        raise BrokerRequestError(f"Alpaca returned an invalid {field} value.")
    return result


def _order_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BrokerRequestError("Alpaca returned an invalid order payload.")
    required = ("id", "client_order_id", "symbol", "side", "qty", "limit_price", "status")
    if any(key not in payload for key in required):
        raise BrokerRequestError("Alpaca returned an incomplete order payload.")
    return {
        "id": str(payload["id"]),
        "client_order_id": str(payload["client_order_id"]),
        "symbol": str(payload["symbol"]),
        "side": str(payload["side"]),
        "qty": str(payload["qty"]),
        "limit_price": str(payload["limit_price"]),
        "status": str(payload["status"]),
    }


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
        # Callers can only select the two constants in this module; redirects are explicitly disabled.
        if base_url not in {PAPER_TRADING_URL, MARKET_DATA_URL}:
            raise BrokerRequestError("Rejected unapproved broker API host.")
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
        if not isinstance(data, dict):
            raise BrokerRequestError("Alpaca returned an invalid account payload.")
        return {
            "status": str(data.get("status", "unknown")),
            "currency": str(data.get("currency", "USD")),
            "equity": _number(data.get("equity", 0), "equity"),
            "last_equity": _number(data.get("last_equity", 0), "last equity"),
            "buying_power": _number(data.get("buying_power", 0), "buying power"),
            "trading_blocked": bool(data.get("trading_blocked", False)),
        }

    async def get_bars(self, spec: StrategySpec, limit: int = 100) -> list[dict[str, Any]]:
        if not _SYMBOL_RE.fullmatch(spec.symbol):
            raise ValueError("Invalid stock symbol.")
        if spec.timeframe not in {"1Min", "5Min", "15Min", "1Hour", "1Day"}:
            raise ValueError("Unsupported Alpaca timeframe.")
        if not 10 <= limit <= 1000:
            raise ValueError("Bar limit must be between 10 and 1000.")
        payload = await self._json_request(
            base_url=MARKET_DATA_URL, method="GET", path=f"/v2/stocks/{spec.symbol}/bars",
            params={"timeframe": spec.timeframe, "limit": limit, "feed": "iex"},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("bars", []), list):
            raise BrokerRequestError("Alpaca returned an invalid bars payload.")
        bars: list[dict[str, Any]] = []
        for bar in payload.get("bars", []):
            if not isinstance(bar, dict) or not all(key in bar for key in ("t", "o", "h", "l", "c")):
                raise BrokerRequestError("Alpaca returned an incomplete market bar.")
            try:
                candle = Candle.model_validate({
                    "timestamp": bar["t"],
                    "open": bar["o"],
                    "high": bar["h"],
                    "low": bar["l"],
                    "close": bar["c"],
                    "volume": bar.get("v", 0),
                })
            except (ValidationError, TypeError, ValueError) as exc:
                raise BrokerRequestError("Alpaca returned an invalid market bar.") from exc
            bars.append(candle.model_dump(mode="json"))
        # Prevent an upstream response with unsorted timestamps changing crossover semantics.
        bars.sort(key=lambda bar: bar["timestamp"])
        return bars

    async def get_position(self, symbol: str) -> dict[str, Any] | None:
        if not _SYMBOL_RE.fullmatch(symbol):
            raise ValueError("Invalid stock symbol.")
        payload = await self._json_request(
            base_url=PAPER_TRADING_URL, method="GET", path=f"/v2/positions/{symbol}",
            not_found_is_none=True,
        )
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise BrokerRequestError("Alpaca returned an invalid position payload.")
        return {
            "symbol": str(payload.get("symbol", symbol)),
            "qty": _number(payload.get("qty", 0), "position quantity", allow_negative=True),
            "side": str(payload.get("side", "unknown")).lower(),
            "market_value": _number(payload.get("market_value", 0), "position market value", allow_negative=True),
        }

    async def get_order_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        if not _ORDER_ID_RE.fullmatch(client_order_id):
            raise ValueError("Invalid client order id.")
        payload = await self._json_request(
            base_url=PAPER_TRADING_URL,
            method="GET",
            path="/v2/orders:by_client_order_id",
            params={"client_order_id": client_order_id},
            not_found_is_none=True,
        )
        return None if payload is None else _order_summary(payload)

    @staticmethod
    def order_matches(
        order: dict[str, Any], *, symbol: str, side: str, quantity: float, limit_price: float,
    ) -> bool:
        try:
            return (
                order["symbol"] == symbol
                and order["side"].lower() == side
                and math.isclose(float(order["qty"]), round(quantity, 6), rel_tol=0, abs_tol=0.000001)
                and math.isclose(float(order["limit_price"]), round(limit_price, 4), rel_tol=0, abs_tol=0.0001)
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            return False

    async def submit_limit_order(
        self, *, symbol: str, side: str, quantity: float, limit_price: float, client_order_id: str
    ) -> dict[str, Any]:
        if not _SYMBOL_RE.fullmatch(symbol):
            raise ValueError("Invalid stock symbol.")
        if side not in {"buy", "sell"} or not math.isfinite(quantity) or not math.isfinite(limit_price):
            raise ValueError("Invalid limit order values.")
        quantity = round(quantity, 6)
        limit_price = round(limit_price, 4)
        if quantity < 0.000001 or limit_price < 0.01:
            raise ValueError("Quantity or limit price is below supported precision.")
        if not _ORDER_ID_RE.fullmatch(client_order_id):
            raise ValueError("Invalid client order id.")

        existing = await self.get_order_by_client_order_id(client_order_id)
        if existing:
            if not self.order_matches(existing, symbol=symbol, side=side, quantity=quantity, limit_price=limit_price):
                raise BrokerOrderConflict("This client order id already belongs to a different order.")
            return existing

        body = {
            "symbol": symbol,
            "qty": f"{quantity:.6f}".rstrip("0").rstrip("."),
            "side": side,
            "type": "limit",
            "time_in_force": "day",
            "limit_price": f"{limit_price:.4f}".rstrip("0").rstrip("."),
            "client_order_id": client_order_id,
        }
        try:
            payload = await self._json_request(
                base_url=PAPER_TRADING_URL, method="POST", path="/v2/orders", json_body=body,
            )
            order = _order_summary(payload)
        except BrokerRequestError as submit_error:
            # The broker may have accepted an order even if the response was lost. Reconcile by the
            # stable client order ID before returning a failure, so a retry cannot place a second order.
            try:
                existing = await self.get_order_by_client_order_id(client_order_id)
            except BrokerRequestError:
                raise submit_error from None
            if existing and self.order_matches(
                existing, symbol=symbol, side=side, quantity=quantity, limit_price=limit_price
            ):
                return existing
            if existing:
                raise BrokerOrderConflict("This client order id already belongs to a different order.") from None
            raise submit_error from None

        if not self.order_matches(order, symbol=symbol, side=side, quantity=quantity, limit_price=limit_price):
            raise BrokerRequestError("Alpaca order response did not match the requested order.")
        return order
