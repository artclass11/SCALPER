"""Small broker adapter contract for future independently reviewed connectors."""

from __future__ import annotations

from typing import Any, Protocol

from scalper.schemas import StrategySpec


class BrokerAdapter(Protocol):
    async def get_account(self) -> dict[str, Any]: ...
    async def get_bars(self, spec: StrategySpec, limit: int = 100) -> list[dict[str, Any]]: ...
    async def get_position(self, symbol: str) -> dict[str, Any] | None: ...
    async def submit_limit_order(
        self, *, symbol: str, side: str, quantity: float, limit_price: float, client_order_id: str
    ) -> dict[str, Any]: ...
