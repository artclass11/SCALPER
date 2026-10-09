import asyncio
from datetime import datetime, timedelta, timezone

from scalper.storage import set_strategy_active
from scalper.worker import _closed_bars, _crossover, process_strategy


def test_worker_detects_latest_upward_cross():
    closes = [10, 9, 8, 7, 7, 7, 7, 7, 7, 30]
    assert _crossover(closes, fast_period=2, slow_period=4) == "buy"


def test_worker_detects_latest_downward_cross():
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


def test_worker_does_not_submit_sell_or_buy_when_account_position_is_short(client, monkeypatch):
    spec = {"name": "Test EMA 2/4", "symbol": "SPY", "timeframe": "1Day",
            "fast_ema": 2, "slow_ema": 4, "strategy_type": "ema_crossover"}
    created_response = client.post("/api/strategies", json={"name": "Short guard", "spec": spec})
    assert created_response.status_code == 200
    item = created_response.json()
    set_strategy_active(item["id"], True)

    now = datetime.now(timezone.utc)
    closes = [10, 9, 8, 7, 7, 7, 7, 7, 7, 30]
    bars = []
    for index, close in enumerate(closes):
        stamp = (now - timedelta(days=(len(closes) - index + 1))).isoformat()
        bars.append({"timestamp": stamp, "open": close, "high": close + 1,
                     "low": max(0.01, close - 1), "close": close, "volume": 1000})

    class FakeBroker:
        submissions = 0
        def __init__(self): pass
        async def get_bars(self, strategy, limit=100): return bars
        async def get_account(self):
            return {"equity": 10000.0, "last_equity": 10000.0, "trading_blocked": False}
        async def get_position(self, symbol):
            return {"symbol": symbol, "qty": 2.0, "side": "short", "market_value": -200.0}
        async def submit_limit_order(self, **kwargs):
            self.submissions += 1
            raise AssertionError("Worker must never add to or reinterpret a short position.")

    monkeypatch.setattr("scalper.worker.AlpacaPaperBroker", FakeBroker)
    asyncio.run(process_strategy(item))
    assert FakeBroker.submissions == 0


def test_inactive_strategy_is_rechecked_before_submission(client, monkeypatch):
    spec = {"name": "Test EMA 2/4", "symbol": "SPY", "timeframe": "1Day",
            "fast_ema": 2, "slow_ema": 4, "strategy_type": "ema_crossover"}
    created_response = client.post("/api/strategies", json={"name": "Inactive guard", "spec": spec})
    assert created_response.status_code == 200
    item = created_response.json()

    now = datetime.now(timezone.utc)
    closes = [10, 9, 8, 7, 7, 7, 7, 7, 7, 30]
    bars = [
        {"timestamp": (now - timedelta(days=(len(closes) - idx + 1))).isoformat(),
         "open": close, "high": close + 1, "low": max(0.01, close - 1),
         "close": close, "volume": 1000}
        for idx, close in enumerate(closes)
    ]

    class FakeBroker:
        submissions = 0
        def __init__(self): pass
        async def get_bars(self, strategy, limit=100): return bars
        async def get_account(self):
            return {"equity": 10000.0, "last_equity": 10000.0, "trading_blocked": False}
        async def get_position(self, symbol): return None
        async def submit_limit_order(self, **kwargs):
            self.submissions += 1
            raise AssertionError("Inactive strategy must not submit.")

    monkeypatch.setattr("scalper.worker.AlpacaPaperBroker", FakeBroker)
    asyncio.run(process_strategy(item))
    assert FakeBroker.submissions == 0
