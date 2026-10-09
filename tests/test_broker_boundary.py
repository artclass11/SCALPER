import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from scalper.brokers import alpaca_paper
from scalper.brokers.alpaca_paper import (
    AlpacaPaperBroker,
    BrokerConfigurationError,
    BrokerOrderConflict,
    BrokerRequestError,
    _order_summary,
)


def test_broker_uses_only_paper_trading_host():
    assert alpaca_paper.PAPER_TRADING_URL == "https://paper-api.alpaca.markets"
    assert alpaca_paper.MARKET_DATA_URL == "https://data.alpaca.markets"
    source = Path(alpaca_paper.__file__).read_text(encoding="utf-8")
    assert "https://api.alpaca.markets" not in source
    assert '"type": "limit"' in source


def test_broker_fails_closed_without_paper_credentials(monkeypatch):
    monkeypatch.delenv("SCALPER_ALPACA_PAPER_KEY", raising=False)
    monkeypatch.delenv("SCALPER_ALPACA_PAPER_SECRET", raising=False)
    with pytest.raises(BrokerConfigurationError):
        AlpacaPaperBroker()


def test_symbols_cannot_escape_api_path():
    broker = object.__new__(AlpacaPaperBroker)
    for symbol in ("../account", "/orders", "SPY/../account", "A B", "$SPY"):
        with pytest.raises(ValueError, match="Invalid stock symbol"):
            asyncio.run(broker.get_position(symbol))


def test_order_id_conflict_is_a_specific_broker_error():
    assert issubclass(BrokerOrderConflict, BrokerRequestError)


def test_order_summary_rejects_incomplete_broker_payload():
    with pytest.raises(BrokerRequestError, match="incomplete order payload"):
        _order_summary({"id": "only-id"})


def test_order_matching_rejects_different_size_or_side():
    order = {"symbol": "SPY", "side": "buy", "qty": "1", "limit_price": "100.00"}
    assert AlpacaPaperBroker.order_matches(order, symbol="SPY", side="buy", quantity=1, limit_price=100)
    assert not AlpacaPaperBroker.order_matches(order, symbol="SPY", side="sell", quantity=1, limit_price=100)
    assert not AlpacaPaperBroker.order_matches(order, symbol="SPY", side="buy", quantity=2, limit_price=100)


def test_existing_order_id_is_idempotent_and_does_not_submit_again():
    broker = object.__new__(AlpacaPaperBroker)
    existing = {"id": "existing-id", "client_order_id": "scalper-unit-order1", "symbol": "SPY",
                "side": "buy", "qty": "1", "limit_price": "100", "status": "accepted"}
    broker.get_order_by_client_order_id = AsyncMock(return_value=existing)
    broker._json_request = AsyncMock(side_effect=AssertionError("Duplicate POST must not be attempted"))
    result = asyncio.run(broker.submit_limit_order(
        symbol="SPY", side="buy", quantity=1, limit_price=100, client_order_id="scalper-unit-order1"
    ))
    assert result == existing
    broker._json_request.assert_not_called()


def test_same_order_id_cannot_be_reused_for_different_order():
    broker = object.__new__(AlpacaPaperBroker)
    existing = {"id": "existing-id", "client_order_id": "scalper-unit-order1", "symbol": "SPY",
                "side": "buy", "qty": "1", "limit_price": "100", "status": "accepted"}
    broker.get_order_by_client_order_id = AsyncMock(return_value=existing)
    with pytest.raises(BrokerOrderConflict):
        asyncio.run(broker.submit_limit_order(
            symbol="SPY", side="sell", quantity=1, limit_price=100, client_order_id="scalper-unit-order1"
        ))


def test_zero_after_precision_rounding_is_rejected():
    broker = object.__new__(AlpacaPaperBroker)
    broker.get_order_by_client_order_id = AsyncMock(side_effect=AssertionError("Must reject before network call"))
    with pytest.raises(ValueError, match="precision"):
        asyncio.run(broker.submit_limit_order(
            symbol="SPY", side="buy", quantity=0.0000001, limit_price=100,
            client_order_id="scalper-unit-order1",
        ))
