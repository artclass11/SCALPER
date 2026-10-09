import pytest

from scalper.strategy import UnsupportedStrategy, parse_strategy


def test_parses_ema_periods_symbol_and_timeframe():
    spec = parse_strategy("EMA 9 crosses above EMA 21 on SPY, 5 minute bars")
    assert (spec.fast_ema, spec.slow_ema) == (9, 21)
    assert spec.symbol == "SPY"
    assert spec.timeframe == "5Min"


def test_defaults_when_unspecified():
    spec = parse_strategy("Build an EMA crossover strategy")
    assert (spec.symbol, spec.timeframe, spec.fast_ema, spec.slow_ema) == ("SPY", "1Day", 9, 21)


def test_rejects_unsupported_indicator():
    with pytest.raises(UnsupportedStrategy, match="EMA crossover"):
        parse_strategy("Use RSI 14 below 30")


def test_periods_are_normalized_to_fast_and_slow():
    spec = parse_strategy("EMA 50 crosses above EMA 9 on SPY")
    assert (spec.fast_ema, spec.slow_ema) == (9, 50)


def test_lowercase_symbol_is_normalized():
    assert parse_strategy("EMA 8 crosses above EMA 34 on aapl").symbol == "AAPL"


def test_prompt_length_is_bounded():
    with pytest.raises(UnsupportedStrategy):
        parse_strategy("EMA " + "1" * 600)
