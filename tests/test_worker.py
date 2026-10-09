from datetime import datetime, timedelta, timezone

from scalper.worker import _closed_bars, _crossover


def test_worker_detects_latest_upward_cross():
    closes = [10, 9, 8, 7, 7, 7, 7, 7, 7, 30]
    assert _crossover(closes, fast_period=2, slow_period=4) == "buy"


def test_worker_detects_latest_downward_cross():
    # Down-cross occurs on the final bar, after a sustained rise.
    closes = [5, 6, 7, 8, 9, 10, 11, 12, 13, 1]
    assert _crossover(closes, fast_period=2, slow_period=4) == "sell"


def test_worker_ignores_open_or_malformed_bars():
    now = datetime.now(timezone.utc)
    old = (now - timedelta(minutes=10)).isoformat()
    future = (now + timedelta(minutes=10)).isoformat()
    bars = [
        {"timestamp": old, "close": 10},
        {"timestamp": future, "close": 11},
        {"timestamp": "not-a-date", "close": 12},
    ]
    assert _closed_bars(bars, "1Min") == [bars[0]]
