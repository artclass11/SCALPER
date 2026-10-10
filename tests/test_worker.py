import asyncio
from datetime import datetime, timedelta, timezone

from scalper.storage import set_strategy_active
from scalper.worker import (
    _closed_bars,
    _crossover,
    _legacy_worker_client_order_id,
    _submit_worker_limit_order,
    _worker_client_order_id,
    process_strategy,
)


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

    processed_bars = []
    monkeypatch.setattr("scalper.worker.update_processed_bar",
                        lambda strategy_id, timestamp: processed_bars.append((strategy_id, timestamp)))
    monkeypatch.setattr("scalper.worker.AlpacaPaperBroker", FakeBroker)
    asyncio.run(process_strategy(item))
    assert FakeBroker.submissions == 0
    assert len(processed_bars) == 1
    assert processed_bars[0][0] == item["id"]


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



def test_closed_bars_are_sorted_deduplicated_and_normalized():
    now = datetime.now(timezone.utc)
    newer = (now - timedelta(minutes=20)).isoformat()
    older = (now - timedelta(minutes=30)).isoformat()
    bars = [
        {"timestamp": newer, "close": 20},
        {"timestamp": older.replace("+00:00", "Z"), "close": 10},
        {"timestamp": older, "close": 11},
    ]
    closed = _closed_bars(bars, "1Min")
    assert [bar["close"] for bar in closed] == [10, 20]
    assert [bar["timestamp"] for bar in closed] == [older.replace("+00:00", "Z"), newer]


def test_worker_order_id_uses_long_unique_strategy_prefix_and_stays_within_broker_limit():
    first_id = "12345678-1234-4234-8234-123456789abc"
    second_id = "12345678-9999-4234-8234-123456789abc"
    stamp = "2026-10-10T07:15:00+00:00"
    first = _worker_client_order_id(first_id, "buy", stamp)
    second = _worker_client_order_id(second_id, "buy", stamp)
    assert first != second
    assert len(first) <= 48
    assert len(first) >= 8
    assert _worker_client_order_id(first_id, "buy", stamp) == first


def test_worker_order_id_rejects_invalid_side():
    import pytest
    with pytest.raises(ValueError, match="Unsupported order side"):
        _worker_client_order_id("12345678-abcd", "cover", "2026-10-10T07:15:00+00:00")



def test_worker_reconciles_existing_legacy_order_before_new_order_id():
    strategy_id = "12345678-1234-4234-8234-123456789abc"
    spec = {"name": "Test EMA 2/4", "symbol": "SPY", "timeframe": "1Day",
            "fast_ema": 2, "slow_ema": 4, "strategy_type": "ema_crossover"}
    from scalper.schemas import StrategySpec
    validated_spec = StrategySpec.model_validate(spec)
    stamp = "2026-10-10T07:15:00Z"
    legacy_id = _legacy_worker_client_order_id(strategy_id, "buy", stamp)
    existing = {"id": "order-existing", "symbol": "SPY", "side": "buy",
                "qty": "2", "limit_price": "100", "status": "accepted"}

    class FakeBroker:
        async def get_order_by_client_order_id(self, client_order_id):
            assert client_order_id == legacy_id
            return existing
        @staticmethod
        def order_matches(order, **kwargs):
            return (order["symbol"] == kwargs["symbol"] and order["side"] == kwargs["side"]
                    and float(order["qty"]) == kwargs["quantity"]
                    and float(order["limit_price"]) == kwargs["limit_price"])
        async def submit_limit_order(self, **kwargs):
            raise AssertionError("Must not submit a second order for an old idempotency key.")

    result = asyncio.run(_submit_worker_limit_order(
        FakeBroker(), strategy_id=strategy_id, spec=validated_spec, side="buy",
        quantity=2, limit_price=100, bar_timestamp=stamp,
    ))
    assert result == existing


def test_worker_fails_closed_if_legacy_order_id_belongs_to_different_order():
    import pytest
    from scalper.brokers.alpaca_paper import BrokerOrderConflict
    from scalper.schemas import StrategySpec

    strategy_id = "12345678-1234-4234-8234-123456789abc"
    spec = StrategySpec(name="Test EMA 2/4", symbol="SPY", fast_ema=2, slow_ema=4)
    stamp = "2026-10-10T07:15:00Z"

    class FakeBroker:
        async def get_order_by_client_order_id(self, client_order_id):
            return {"id": "conflict", "symbol": "AAPL", "side": "buy",
                    "qty": "2", "limit_price": "100", "status": "accepted"}
        @staticmethod
        def order_matches(order, **kwargs): return False
        async def submit_limit_order(self, **kwargs):
            raise AssertionError("A conflicting legacy key must never trigger submission.")

    with pytest.raises(BrokerOrderConflict):
        asyncio.run(_submit_worker_limit_order(
            FakeBroker(), strategy_id=strategy_id, spec=spec, side="buy",
            quantity=2, limit_price=100, bar_timestamp=stamp,
        ))



def test_worker_uses_extended_id_when_no_legacy_order_exists():
    from scalper.schemas import StrategySpec

    strategy_id = "12345678-1234-4234-8234-123456789abc"
    spec = StrategySpec(name="Test EMA 2/4", symbol="SPY", fast_ema=2, slow_ema=4)
    stamp = "2026-10-10T07:15:00Z"

    class FakeBroker:
        queried_id = None
        submitted = None
        async def get_order_by_client_order_id(self, client_order_id):
            self.queried_id = client_order_id
            return None
        async def submit_limit_order(self, **kwargs):
            self.submitted = kwargs
            return {"status": "accepted", **kwargs}

    broker = FakeBroker()
    result = asyncio.run(_submit_worker_limit_order(
        broker, strategy_id=strategy_id, spec=spec, side="buy",
        quantity=2, limit_price=100, bar_timestamp=stamp,
    ))
    assert broker.queried_id == _legacy_worker_client_order_id(strategy_id, "buy", stamp)
    assert broker.submitted["client_order_id"] == _worker_client_order_id(strategy_id, "buy", stamp)
    assert len(broker.submitted["client_order_id"]) <= 48
    assert result["status"] == "accepted"



def test_worker_checkpoints_and_records_legacy_order_conflict(client, monkeypatch):
    spec = {"name": "Test EMA 2/4", "symbol": "SPY", "timeframe": "1Day",
            "fast_ema": 2, "slow_ema": 4, "strategy_type": "ema_crossover"}
    created = client.post("/api/strategies", json={"name": "Legacy conflict", "spec": spec})
    assert created.status_code == 200
    item = created.json()
    set_strategy_active(item["id"], True)

    now = datetime.now(timezone.utc)
    closes = [10, 9, 8, 7, 7, 7, 7, 7, 7, 30]
    bars = [
        {"timestamp": (now - timedelta(days=(len(closes) - idx + 1))).isoformat(),
         "open": close, "high": close + 1, "low": max(0.01, close - 1),
         "close": close, "volume": 1000}
        for idx, close in enumerate(closes)
    ]

    class FakeBroker:
        def __init__(self): pass
        async def get_bars(self, strategy, limit=100): return bars
        async def get_account(self):
            return {"equity": 10000.0, "last_equity": 10000.0, "trading_blocked": False}
        async def get_position(self, symbol): return None
        async def get_order_by_client_order_id(self, client_order_id):
            return {"id": "legacy-conflict", "symbol": "AAPL", "side": "buy",
                    "qty": "2", "limit_price": "100", "status": "accepted"}
        @staticmethod
        def order_matches(order, **kwargs): return False
        async def submit_limit_order(self, **kwargs):
            raise AssertionError("A conflicting legacy ID must never submit a second order.")

    monkeypatch.setattr("scalper.worker.AlpacaPaperBroker", FakeBroker)
    asyncio.run(process_strategy(item))
    saved = client.get("/api/strategies").json()[0]
    assert saved["last_processed_bar"] == bars[-1]["timestamp"]
    assert saved["last_error"] == "LegacyOrderConflict"
