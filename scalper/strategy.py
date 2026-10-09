"""Safe natural-language parser. It never evaluates generated code."""

from __future__ import annotations

import re

from scalper.schemas import StrategySpec


class UnsupportedStrategy(ValueError):
    """Raised when the prompt cannot be represented by the allow-listed DSL."""


_PERIOD = re.compile(r"\bema\s*(\d{1,3})\b|\b(\d{1,3})\s*ema\b", re.IGNORECASE)
_SYMBOL = re.compile(r"\b(?:on|for|symbol)\s+\$?([A-Z][A-Z0-9.-]{0,14})\b", re.IGNORECASE)
_TIMEFRAME = re.compile(r"\b(1|5|15)\s*(?:m|min|mins|minute|minutes)\b", re.IGNORECASE)


def parse_strategy(prompt: str) -> StrategySpec:
    if not isinstance(prompt, str) or not 3 <= len(prompt.strip()) <= 500:
        raise UnsupportedStrategy("Prompt must contain between 3 and 500 characters.")
    text = prompt.strip()
    lower = text.lower()
    if any(term in lower for term in ("rsi", "macd", "bollinger")):
        raise UnsupportedStrategy("This release supports EMA crossover strategies only. Code is never executed.")
    if not any(term in lower for term in ("ema", "exponential moving average", "crossover", "cross over")):
        raise UnsupportedStrategy("Describe an EMA crossover, for example: EMA 9 crosses above EMA 21 on SPY.")

    hits = [(match.start(), int(match.group(1) or match.group(2))) for match in _PERIOD.finditer(text)]
    periods = [value for _, value in sorted(hits)]
    if len(periods) >= 2:
        fast, slow = sorted(periods[:2])
    elif len(periods) == 1:
        fast, slow = (periods[0], 21) if periods[0] < 21 else (9, periods[0])
    else:
        fast, slow = 9, 21

    if fast < 2 or fast > 200 or slow > 500 or fast >= slow:
        raise UnsupportedStrategy("Choose fast EMA from 2–200 and slow EMA greater than fast (max 500).")

    symbol_match = _SYMBOL.search(text)
    symbol = symbol_match.group(1).upper() if symbol_match else "SPY"
    frame_match = _TIMEFRAME.search(text)
    if frame_match:
        timeframe = {"1": "1Min", "5": "5Min", "15": "15Min"}[frame_match.group(1)]
    elif re.search(r"\b(?:1|one)\s*(?:hour|hr|h)\b", lower):
        timeframe = "1Hour"
    elif re.search(r"\b(?:daily|1\s*day|one day)\b", lower):
        timeframe = "1Day"
    else:
        timeframe = "1Day"

    return StrategySpec(
        name=f"EMA {fast}/{slow} crossover on {symbol}",
        # The input is capped at 500 characters too, but keep the decorated description bounded.
        description=(f"Long-only EMA crossover parsed from user text: {text}")[:500],
        symbol=symbol,
        timeframe=timeframe,
        fast_ema=fast,
        slow_ema=slow,
    )
