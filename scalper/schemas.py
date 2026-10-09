"""Validated contracts shared by API, engine, MCP and broker adapters."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Timeframe = Literal["1Min", "5Min", "15Min", "1Hour", "1Day"]
SYMBOL_PATTERN = r"^[A-Z][A-Z0-9.-]{0,14}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StrategySpec(StrictModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    symbol: str = Field(default="SPY", pattern=SYMBOL_PATTERN)
    timeframe: Timeframe = "1Day"
    fast_ema: int = Field(default=9, ge=2, le=200)
    slow_ema: int = Field(default=21, ge=3, le=500)
    strategy_type: Literal["ema_crossover"] = "ema_crossover"

    @model_validator(mode="after")
    def validate_periods(self) -> StrategySpec:
        if self.fast_ema >= self.slow_ema:
            raise ValueError("fast_ema must be lower than slow_ema")
        return self


class StrategyPrompt(StrictModel):
    prompt: str = Field(min_length=3, max_length=500)


class SaveStrategyRequest(StrictModel):
    name: str = Field(min_length=2, max_length=80)
    spec: StrategySpec


class ActivationRequest(StrictModel):
    confirmed: Literal[True]


class Candle(StrictModel):
    timestamp: datetime
    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)
    volume: float = Field(default=0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_ohlc(self) -> Candle:
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be greater than or equal to open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be less than or equal to open, close, and high")
        return self


class BacktestRequest(StrictModel):
    spec: StrategySpec
    candles: list[Candle] = Field(min_length=10, max_length=10000)
    starting_cash: float = Field(default=100000, gt=0, le=1000000000, allow_inf_nan=False)
    position_fraction: float = Field(default=0.1, gt=0, le=0.5, allow_inf_nan=False)
    fee_bps: float = Field(default=1.0, ge=0, le=100, allow_inf_nan=False)
    slippage_bps: float = Field(default=1.0, ge=0, le=100, allow_inf_nan=False)


class RiskCheckRequest(StrictModel):
    symbol: str = Field(pattern=SYMBOL_PATTERN)
    side: Literal["buy", "sell"]
    quantity: float = Field(ge=0.000001, le=1000000, allow_inf_nan=False)
    limit_price: float = Field(gt=0, le=1000000, allow_inf_nan=False)
    account_equity: float = Field(gt=0, le=1000000000, allow_inf_nan=False)
    daily_pnl_pct: float = Field(default=0, ge=-100, le=100, allow_inf_nan=False)
    reduce_only: bool = False


class PaperLimitOrderRequest(StrictModel):
    symbol: str = Field(pattern=SYMBOL_PATTERN)
    side: Literal["buy", "sell"]
    quantity: float = Field(ge=0.000001, le=1000000, allow_inf_nan=False)
    limit_price: float = Field(ge=0.01, le=1000000, allow_inf_nan=False)
    confirmed: Literal[True]
    client_order_id: str | None = Field(default=None, min_length=8, max_length=48)

    @model_validator(mode="after")
    def validate_client_order_id(self) -> PaperLimitOrderRequest:
        if self.client_order_id and not re.fullmatch(r"[A-Za-z0-9._:-]{8,48}", self.client_order_id):
            raise ValueError("client_order_id contains unsupported characters")
        return self
