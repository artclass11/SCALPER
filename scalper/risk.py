"""Fail-closed risk checks shared by the paper API and worker."""

from __future__ import annotations

import math
import os
import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: tuple[str, ...]
    order_notional: float
    permitted_notional: float

    def as_dict(self) -> dict:
        return asdict(self)


def _setting(name: str, default: float) -> float:
    try:
        number = float(os.getenv(name, str(default)))
        return number if math.isfinite(number) and number > 0 else default
    except ValueError:
        return default


def check_limit_order(
    *,
    symbol: str,
    side: str,
    quantity: float,
    limit_price: float,
    account_equity: float,
    daily_pnl_pct: float = 0.0,
    reduce_only: bool = False,
    kill_switch: bool | None = None,
) -> RiskDecision:
    reasons: list[str] = []
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9./_-]{1,20}", symbol):
        reasons.append("invalid_symbol")
    if side not in {"buy", "sell"}:
        reasons.append("invalid_side")
    nums = [quantity, limit_price, account_equity, daily_pnl_pct]
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in nums):
        reasons.append("non_finite_numeric_input")
    if quantity <= 0 or limit_price <= 0:
        reasons.append("quantity_and_price_must_be_positive")
    if account_equity <= 0:
        reasons.append("account_equity_must_be_positive")

    notional = max(quantity, 0.0) * max(limit_price, 0.0)
    absolute_limit = _setting("SCALPER_MAX_ORDER_NOTIONAL", 2500.0)
    max_position_pct = min(_setting("SCALPER_MAX_POSITION_PCT", 5.0), 100.0)
    daily_loss_limit = min(_setting("SCALPER_MAX_DAILY_LOSS_PCT", 2.0), 100.0)
    permitted = min(absolute_limit, max(account_equity, 0.0) * max_position_pct / 100.0)
    kill = kill_switch if kill_switch is not None else (
        os.getenv("SCALPER_KILL_SWITCH", "").strip().lower() in {"1", "true", "yes", "on"}
    )

    if kill and not reduce_only:
        reasons.append("kill_switch_enabled")
    if not reduce_only and daily_pnl_pct <= -daily_loss_limit:
        reasons.append("daily_loss_limit_reached")
    if not reduce_only and notional > permitted:
        reasons.append("order_exceeds_permitted_notional")
    if notional <= 0:
        reasons.append("order_notional_must_be_positive")

    return RiskDecision(
        approved=not reasons,
        reasons=tuple(reasons),
        order_notional=round(notional, 4),
        permitted_notional=round(permitted, 4),
    )
