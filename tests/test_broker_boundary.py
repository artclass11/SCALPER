from pathlib import Path

import pytest

from scalper.brokers import alpaca_paper
from scalper.brokers.alpaca_paper import AlpacaPaperBroker, BrokerConfigurationError


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
