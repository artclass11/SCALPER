"""MCP tools for strategy planning and backtesting; no trade execution tools."""

from __future__ import annotations

import json


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit('Install MCP support with: pip install -e ".[mcp]"') from exc

    from scalper.backtest import run_backtest
    from scalper.schemas import Candle, StrategySpec
    from scalper.storage import list_strategies
    from scalper.strategy import UnsupportedStrategy, parse_strategy

    server = FastMCP("SCALPER")

    @server.tool()
    def build_strategy_spec(prompt: str) -> str:
        """Convert plain language to the supported, non-executable EMA strategy schema."""
        try:
            return parse_strategy(prompt).model_dump_json()
        except UnsupportedStrategy as exc:
            return json.dumps({"error": str(exc)})

    @server.tool()
    def backtest_ema_strategy(strategy_json: str, candles_json: str, starting_cash: float = 100000) -> str:
        """Backtest a strategy against caller-supplied OHLCV bars; never places an order."""
        try:
            spec = StrategySpec.model_validate_json(strategy_json)
            payload = json.loads(candles_json)
            candles = [Candle.model_validate(row) for row in payload]
            return json.dumps(run_backtest(spec, candles, starting_cash=starting_cash), separators=(",", ":"))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return json.dumps({"error": f"Invalid input: {type(exc).__name__}"})

    @server.tool()
    def list_saved_strategies() -> str:
        """List saved strategy specifications and activation state, without credentials."""
        return json.dumps(list_strategies(), separators=(",", ":"))

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
