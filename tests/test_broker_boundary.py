import asyncio
from pathlib import Path

import pytest

from scalper.brokers import alpaca_paper
from scalper.brokers.alpaca_paper import AlpacaPaperBroker, BrokerConfigurationError, BrokerOrderConflict


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
    assert issubclass(BrokerOrderConflict, Exception)


def test_order_matching_rejects_different_size_or_side():
    order = {"symbol": "SPY", "side": "buy", "qty": "1", "limit_price": "100.00"}
    assert AlpacaPaperBroker.order_matches(order, symbol="SPY", side="buy", quantity=1, limit_price=100)
    assert not AlpacaPaperBroker.order_matches(order, symbol="SPY", side="sell", quantity=1, limit_price=100)
    assert not AlpacaPaperBroker.order_matches(order, symbol="SPY", side="buy", quantity=2, limit_price=100)
