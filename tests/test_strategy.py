import pytest
from pydantic import ValidationError

from scalper.schemas import StrategySpec
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


def test_maximum_length_prompt_does_not_crash_with_validation_error():
    base = "EMA 9 crosses above EMA 21 on SPY "
    prompt = base + ("x" * (500 - len(base)))
    spec = parse_strategy(prompt)
    assert len(spec.description) <= 500


@pytest.mark.parametrize("symbol", ["../account", "/orders", "SPY/../account", "A B", "$SPY"])
def test_strategy_schema_rejects_path_and_non_symbol_input(symbol):
    with pytest.raises(ValidationError):
        StrategySpec(name="Bad symbol", symbol=symbol, fast_ema=9, slow_ema=21)



@pytest.mark.parametrize(
    "prompt",
    [
        "EMA crossover for technology stocks",
        "EMA 9 crosses above EMA 21 for long-term trading",
        "EMA crossover on the market",
        "EMA crossover on a stock portfolio",
        "EMA crossover for EMA signals",
        "EMA crossover for buy signals on a bearish market",
    ],
)
def test_natural_language_descriptors_are_not_misread_as_tickers(prompt):
    assert parse_strategy(prompt).symbol == "SPY"


def test_real_symbol_after_generic_phrase_is_still_found():
    spec = parse_strategy("EMA 9 crosses above EMA 21 on the market, for AAPL")
    assert spec.symbol == "AAPL"
