"""Opt-in separate paper-only background strategy worker."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from scalper.backtest import ema
from scalper.brokers.alpaca_paper import AlpacaPaperBroker, BrokerOrderConflict
from scalper.config import alpaca_paper_configured, env_bool
from scalper.risk import check_limit_order
from scalper.schemas import StrategySpec
from scalper.storage import (
    get_strategy,
    init_db,
    list_strategies,
    update_processed_bar,
    update_strategy_error,
)


def _frame_duration(frame: str) -> timedelta:
    return {"1Min": timedelta(minutes=1), "5Min": timedelta(minutes=5),
            "15Min": timedelta(minutes=15), "1Hour": timedelta(hours=1),
            "1Day": timedelta(days=1)}[frame]


def _closed_bars(bars: list[dict], timeframe: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    duration = _frame_duration(timeframe)
    by_timestamp: dict[datetime, dict] = {}
    for bar in bars:
        try:
            parsed = datetime.fromisoformat(bar["timestamp"].replace("Z", "+00:00"))
            stamp = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
            stamp = stamp.astimezone(timezone.utc)
        except (TypeError, ValueError, KeyError, AttributeError):
            continue
        if now >= stamp + duration + timedelta(seconds=3):
            # Canonical UTC timestamps make duplicate and offset-formatted bars comparable.
            if stamp not in by_timestamp:
                # Preserve the upstream timestamp spelling because older worker versions saved
                # that exact string in SQLite; canonicalize only the internal sort/dedup key.
                by_timestamp[stamp] = dict(bar)
    return [by_timestamp[key] for key in sorted(by_timestamp)]


def _worker_client_order_id(strategy_id: str, side: str, bar_timestamp: str) -> str:
    """Build a stable, broker-safe key with enough strategy entropy for many saved strategies."""
    if side not in {"buy", "sell"}:
        raise ValueError("Unsupported order side.")
    strategy_key = re.sub(r"[^A-Za-z0-9]", "", strategy_id)[:16]
    bar_key = re.sub(r"[^A-Za-z0-9]", "", bar_timestamp)[:20]
    if len(strategy_key) < 8 or len(bar_key) < 8:
        raise ValueError("Could not build a stable paper order id.")
    # Max length is 45 chars (within Alpaca's 48-character limit).
    return f"sc-{strategy_key}-{side}-{bar_key}"



def _legacy_worker_client_order_id(strategy_id: str, side: str, bar_timestamp: str) -> str:
    """Recreate pre-hardening order IDs so uncertain in-flight orders remain reconcilable."""
    if side not in {"buy", "sell"}:
        raise ValueError("Unsupported order side.")
    strategy_key = strategy_id[:8]
    bar_key = re.sub(r"[^A-Za-z0-9]", "", bar_timestamp)[:20]
    if len(strategy_key) < 8 or len(bar_key) < 8:
        raise ValueError("Could not build a legacy paper order id.")
    return f"scalper-{strategy_key}-{side}-{bar_key}"


async def _submit_worker_limit_order(
    broker: AlpacaPaperBroker,
    *,
    strategy_id: str,
    spec: StrategySpec,
    side: str,
    quantity: float,
    limit_price: float,
    bar_timestamp: str,
) -> dict:
    """Reconcile an old order key before using the newer, wider strategy key."""
    legacy_id = _legacy_worker_client_order_id(strategy_id, side, bar_timestamp)
    existing = await broker.get_order_by_client_order_id(legacy_id)
    if existing:
        if not broker.order_matches(
            existing, symbol=spec.symbol, side=side, quantity=quantity, limit_price=limit_price
        ):
            raise BrokerOrderConflict(
                "A previous worker order ID belongs to a different order; refusing a possible duplicate."
            )
        return existing
    return await broker.submit_limit_order(
        symbol=spec.symbol,
        side=side,
        quantity=quantity,
        limit_price=limit_price,
        client_order_id=_worker_client_order_id(strategy_id, side, bar_timestamp),
    )


def _crossover(closes: list[float], fast_period: int, slow_period: int) -> str | None:
    if len(closes) < max(slow_period + 2, 10):
        return None
    fast, slow = ema(closes, fast_period), ema(closes, slow_period)
    if fast[-2] <= slow[-2] and fast[-1] > slow[-1]:
        return "buy"
    if fast[-2] >= slow[-2] and fast[-1] < slow[-1]:
        return "sell"
    return None


async def process_strategy(item: dict) -> None:
    spec = StrategySpec.model_validate(item["spec"])
    broker = AlpacaPaperBroker()
    bars = _closed_bars(
        await broker.get_bars(spec, limit=min(1000, max(100, spec.slow_ema * 4))), spec.timeframe
    )
    if len(bars) < spec.slow_ema + 2:
        return
    latest = bars[-1]
    bar_stamp = latest["timestamp"]
    if item.get("last_processed_bar") == bar_stamp:
        return

    signal = _crossover([bar["close"] for bar in bars], spec.fast_ema, spec.slow_ema)
    account = await broker.get_account()
    position = await broker.get_position(spec.symbol)

    # This strategy intentionally supports long-only stock positions. Never treat a short as
    # flat, because a "sell" signal could otherwise increase a short position.
    if position and position.get("side", "").lower() != "long":
        update_strategy_error(item["id"], "UnsupportedPositionSide")
        # This bar cannot be acted on safely; record the skip to avoid repeating the same
        # account/position calls every polling cycle while waiting for the next completed bar.
        update_processed_bar(item["id"], bar_stamp)
        return
    position_qty = position["qty"] if position and position["qty"] > 0 else 0.0
    order = None

    if signal in {"buy", "sell"}:
        # Re-check the saved activation state just before order handling. A deactivation requested
        # while market data was loading should prevent a stale strategy from placing an order.
        current = get_strategy(item["id"])
        if not current or not current["active"]:
            return

    if signal == "buy" and position_qty <= 0 and not account["trading_blocked"]:
        equity = account["equity"]
        if equity > 0:
            budget = min(equity * 0.02, float(os.getenv("SCALPER_MAX_ORDER_NOTIONAL", "2500")))
            price = max(0.01, round(float(latest["close"]), 2))
            qty = round(budget / price, 6)
            decision = check_limit_order(
                symbol=spec.symbol, side="buy", quantity=qty, limit_price=price, account_equity=equity,
                daily_pnl_pct=((equity / account["last_equity"]) - 1) * 100
                if account["last_equity"] > 0 else 0,
            )
            if decision.approved and not env_bool("SCALPER_KILL_SWITCH"):
                order = await _submit_worker_limit_order(
                    broker, strategy_id=item["id"], spec=spec, side="buy", quantity=qty,
                    limit_price=price, bar_timestamp=bar_stamp,
                )
    elif signal == "sell" and position_qty > 0 and not account["trading_blocked"]:
        price = max(0.01, round(float(latest["close"]), 2))
        decision = check_limit_order(
            symbol=spec.symbol, side="sell", quantity=position_qty, limit_price=price,
            account_equity=max(account["equity"], 1.0), reduce_only=True,
        )
        if decision.approved:
            order = await _submit_worker_limit_order(
                broker, strategy_id=item["id"], spec=spec, side="sell", quantity=position_qty,
                limit_price=price, bar_timestamp=bar_stamp,
            )

    update_processed_bar(item["id"], bar_stamp)
    if order:
        from scalper.storage import record_event
        record_event("paper_order_submitted", item["id"], {"side": order["side"], "status": order["status"]})


async def run_forever() -> None:
    init_db()
    try:
        interval = int(os.getenv("SCALPER_WORKER_INTERVAL_SECONDS", "15"))
    except ValueError:
        interval = 15
    interval = max(5, min(interval, 300))
    while True:
        for item in list_strategies(active_only=True):
            try:
                await process_strategy(item)
            except Exception as exc:
                update_strategy_error(item["id"], type(exc).__name__)
        await asyncio.sleep(interval)


def main() -> None:
    if not env_bool("SCALPER_AUTOMATION_ENABLED"):
        print("Paper automation disabled. Set SCALPER_AUTOMATION_ENABLED=true to start.", file=sys.stderr)
        raise SystemExit(2)
    if not alpaca_paper_configured():
        print("Alpaca paper credentials are not configured.", file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
