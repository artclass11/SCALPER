from datetime import datetime, timedelta, timezone

import pytest

from scalper.backtest import ema, run_backtest
from scalper.schemas import Candle, StrategySpec


def make_candles(closes):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(timestamp=start + timedelta(days=i), open=float(value), high=float(value) + 0.5,
               low=float(value) - 0.5, close=float(value), volume=1000)
        for i, value in enumerate(closes)
    ]


def test_ema_is_deterministic():
    assert ema([10, 10, 10], 2) == [10, 10, 10]


def test_backtest_metrics_and_ledger():
    spec = StrategySpec(name="Test EMA 2/4", symbol="SPY", fast_ema=2, slow_ema=4)
    result = run_backtest(spec, make_candles([10, 9, 8, 7, 8, 9, 11, 12, 10, 8, 7, 6]))
    assert result["starting_cash"] == 100000
    assert result["ending_equity"] > 0
    assert result["trade_count"] >= 1
    assert result["max_drawdown_pct"] <= 0
    assert len(result["trades"]) == result["trade_count"]


def test_costs_cannot_improve_result_for_same_signals():
    spec = StrategySpec(name="Test EMA 2/4", symbol="SPY", fast_ema=2, slow_ema=4)
    candles = make_candles([10, 9, 8, 7, 8, 9, 11, 12, 10, 8, 7, 6])
    free = run_backtest(spec, candles, fee_bps=0, slippage_bps=0)
    costs = run_backtest(spec, candles, fee_bps=5, slippage_bps=5)
    assert costs["ending_equity"] <= free["ending_equity"]


def test_rejects_too_few_bars():
    spec = StrategySpec(name="Test EMA 2/4", symbol="SPY", fast_ema=2, slow_ema=4)
    with pytest.raises(ValueError, match="Provide at least"):
        run_backtest(spec, make_candles([1, 2, 3, 4, 5, 6, 7, 8, 9]))


def test_rejects_non_chronological_candles():
    spec = StrategySpec(name="Test EMA 2/4", symbol="SPY", fast_ema=2, slow_ema=4)
    candles = make_candles([10, 9, 8, 7, 8, 9, 11, 12, 10, 8, 7, 6])
    with pytest.raises(ValueError, match="chronological"):
        run_backtest(spec, list(reversed(candles)))
