"""Deterministic long-only backtester with next-bar-open execution."""

from __future__ import annotations

from datetime import timezone
from typing import Sequence

from scalper.schemas import Candle, StrategySpec


def ema(values: Sequence[float], period: int) -> list[float]:
    if period < 1:
        raise ValueError("EMA period must be positive")
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    result = [float(values[0])]
    for value in values[1:]:
        result.append(alpha * float(value) + (1.0 - alpha) * result[-1])
    return result


def _timestamp(value) -> str:
    stamp = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat()


def run_backtest(
    spec: StrategySpec,
    candles: Sequence[Candle],
    starting_cash: float = 100000.0,
    position_fraction: float = 0.1,
    fee_bps: float = 1.0,
    slippage_bps: float = 1.0,
) -> dict:
    if len(candles) < max(10, spec.slow_ema + 2):
        raise ValueError(f"Provide at least {max(10, spec.slow_ema + 2)} candles for this strategy.")
    if starting_cash <= 0:
        raise ValueError("starting_cash must be positive")
    if not 0 < position_fraction <= 0.5:
        raise ValueError("position_fraction must be in (0, 0.5]")
    if min(fee_bps, slippage_bps) < 0 or max(fee_bps, slippage_bps) > 100:
        raise ValueError("fee and slippage assumptions must be between 0 and 100 basis points")

    closes = [c.close for c in candles]
    fast_values = ema(closes, spec.fast_ema)
    slow_values = ema(closes, spec.slow_ema)
    fee_rate = fee_bps / 10000.0
    slip_rate = slippage_bps / 10000.0
    cash, quantity, position = float(starting_cash), 0.0, None
    trades: list[dict] = []
    equity_points: list[float] = []
    peak_equity, max_drawdown = starting_cash, 0.0

    def close_position(raw_price: float, timestamp: str) -> None:
        nonlocal cash, quantity, position
        assert position is not None
        exit_price = raw_price * (1.0 - slip_rate)
        gross_proceeds = quantity * exit_price
        exit_fee = gross_proceeds * fee_rate
        cash += gross_proceeds - exit_fee
        pnl = gross_proceeds - exit_fee - position["cash_outlay"]
        denominator = max(position["cash_outlay"], 1e-12)
        trades.append({
            "entry_time": position["entry_time"], "exit_time": timestamp,
            "entry_price": round(position["entry_price"], 6), "exit_price": round(exit_price, 6),
            "quantity": round(quantity, 8), "pnl": round(pnl, 2),
            "return_pct": round(100.0 * pnl / denominator, 4), "won": pnl > 0,
        })
        quantity, position = 0.0, None

    for execution_index in range(1, len(candles)):
        signal_index = execution_index - 1
        if signal_index >= spec.slow_ema:
            crossed_up = (
                fast_values[signal_index - 1] <= slow_values[signal_index - 1]
                and fast_values[signal_index] > slow_values[signal_index]
            )
            crossed_down = (
                fast_values[signal_index - 1] >= slow_values[signal_index - 1]
                and fast_values[signal_index] < slow_values[signal_index]
            )
            bar = candles[execution_index]
            if position is None and crossed_up:
                entry_price = bar.open * (1.0 + slip_rate)
                quantity = cash * position_fraction / entry_price
                gross_cost = quantity * entry_price
                entry_fee = gross_cost * fee_rate
                total_outlay = gross_cost + entry_fee
                if total_outlay > cash:
                    quantity = cash / (entry_price * (1.0 + fee_rate))
                    gross_cost = quantity * entry_price
                    entry_fee = gross_cost * fee_rate
                    total_outlay = gross_cost + entry_fee
                cash -= total_outlay
                position = {
                    "entry_time": _timestamp(bar.timestamp),
                    "entry_price": entry_price,
                    "cash_outlay": total_outlay,
                }
            elif position is not None and crossed_down:
                close_position(bar.open, _timestamp(bar.timestamp))

        marked_equity = cash + quantity * candles[execution_index].close
        equity_points.append(marked_equity)
        peak_equity = max(peak_equity, marked_equity)
        max_drawdown = min(max_drawdown, marked_equity / peak_equity - 1.0 if peak_equity else 0.0)

    if position is not None:
        last = candles[-1]
        close_position(last.close, _timestamp(last.timestamp))
        if equity_points:
            equity_points[-1] = cash
        peak_equity = max(peak_equity, cash)
        max_drawdown = min(max_drawdown, cash / peak_equity - 1.0 if peak_equity else 0.0)

    win_count = sum(trade["won"] for trade in trades)
    return {
        "symbol": spec.symbol,
        "strategy": spec.name,
        "starting_cash": round(starting_cash, 2),
        "ending_equity": round(cash, 2),
        "total_return_pct": round((cash / starting_cash - 1.0) * 100.0, 4),
        "max_drawdown_pct": round(max_drawdown * 100.0, 4),
        "trade_count": len(trades),
        "win_rate_pct": round(100.0 * win_count / len(trades), 2) if trades else 0.0,
        "fee_bps_per_side": fee_bps,
        "slippage_bps_per_side": slippage_bps,
        "position_fraction": position_fraction,
        "trades": trades,
        "warning": "Simulation only. Data quality, partial fills, taxes and market impact can change outcomes.",
    }
