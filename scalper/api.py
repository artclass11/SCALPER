"""FastAPI service. Loopback by default; all broker execution is paper-only."""

from __future__ import annotations

import hmac
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from scalper.backtest import run_backtest
from scalper.brokers.alpaca_paper import (
    AlpacaPaperBroker,
    BrokerConfigurationError,
    BrokerOrderConflict,
    BrokerRequestError,
)
from scalper.config import allowed_origins, alpaca_paper_configured, api_token, env_bool
from scalper.risk import check_limit_order
from scalper.schemas import (
    ActivationRequest,
    BacktestRequest,
    PaperLimitOrderRequest,
    RiskCheckRequest,
    SaveStrategyRequest,
    StrategyPrompt,
)
from scalper.storage import (
    delete_strategy,
    get_strategy,
    init_db,
    list_strategies,
    save_strategy,
    set_strategy_active,
)
from scalper.strategy import UnsupportedStrategy, parse_strategy

WEB_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "web"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="SCALPER", version="0.1.0", docs_url=None, redoc_url=None,
    openapi_url="/api/openapi.json", lifespan=lifespan,
)


class SecurityHeadersMiddleware:
    def __init__(self, inner_app) -> None:
        self.inner_app = inner_app

    async def __call__(self, scope, receive, send):
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; "
                     b"img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; "
                     b"frame-ancestors 'none'; form-action 'self'"),
                ])
                if scope.get("path", "").startswith("/api/"):
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await self.inner_app(scope, receive, send_with_headers)


app.add_middleware(SecurityHeadersMiddleware)
origins = allowed_origins()
if origins:
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"], max_age=300,
    )


def _is_local_host_header(host_header: str) -> bool:
    try:
        host = urlsplit("//" + host_header).hostname
    except ValueError:
        return False
    return host is not None and host.lower() in {"127.0.0.1", "localhost", "::1"}


async def require_api_access(
    request: Request, authorization: str | None = Header(default=None)
) -> None:
    client_host = request.client.host if request.client else ""
    if env_bool("SCALPER_TEST_MODE") and client_host == "testclient":
        return

    configured_token = api_token()
    if configured_token:
        supplied = authorization or ""
        if not supplied.startswith("Bearer ") or not hmac.compare_digest(
            supplied.removeprefix("Bearer ").strip(), configured_token
        ):
            raise HTTPException(status_code=401, detail="Authentication required.")
        return

    if client_host in {"127.0.0.1", "::1", "localhost"} and _is_local_host_header(
        request.headers.get("host", "")
    ):
        return
    raise HTTPException(
        status_code=403,
        detail="Remote API access is disabled. Configure a strong SCALPER_API_TOKEN and secure gateway.",
    )


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "SCALPER", "version": "0.1.0"}


@app.get("/api/status", dependencies=[Depends(require_api_access)])
async def status() -> dict[str, Any]:
    return {
        "alpaca_paper_configured": alpaca_paper_configured(),
        "automation_enabled": env_bool("SCALPER_AUTOMATION_ENABLED"),
        "kill_switch_enabled": env_bool("SCALPER_KILL_SWITCH"),
        "ollama_enabled": bool(os.getenv("SCALPER_OLLAMA_MODEL", "").strip()),
        "live_trading_enabled": False,
    }


@app.post("/api/strategies/parse", dependencies=[Depends(require_api_access)])
async def parse_prompt(request: StrategyPrompt) -> dict:
    try:
        spec = parse_strategy(request.prompt)
    except UnsupportedStrategy as exc:
        if not os.getenv("SCALPER_OLLAMA_MODEL", "").strip():
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        from scalper.ai.ollama import LocalModelError, parse_with_ollama
        try:
            spec = await parse_with_ollama(request.prompt)
        except LocalModelError as model_error:
            raise HTTPException(status_code=422, detail=str(model_error)) from model_error
    return spec.model_dump()


@app.get("/api/strategies", dependencies=[Depends(require_api_access)])
async def strategies() -> list[dict]:
    return list_strategies()


@app.post("/api/strategies", dependencies=[Depends(require_api_access)])
async def create_strategy(request: SaveStrategyRequest) -> dict:
    return save_strategy(request.name, request.spec)


@app.post("/api/strategies/{strategy_id}/activate", dependencies=[Depends(require_api_access)])
async def activate_strategy(strategy_id: str, request: ActivationRequest) -> dict:
    if not env_bool("SCALPER_AUTOMATION_ENABLED"):
        raise HTTPException(status_code=409, detail="Set SCALPER_AUTOMATION_ENABLED=true and restart the worker.")
    if not alpaca_paper_configured():
        raise HTTPException(status_code=409, detail="Alpaca paper credentials are not configured.")
    item = set_strategy_active(strategy_id, True)
    if item is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return item


@app.post("/api/strategies/{strategy_id}/deactivate", dependencies=[Depends(require_api_access)])
async def deactivate_strategy(strategy_id: str) -> dict:
    item = set_strategy_active(strategy_id, False)
    if item is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return item


@app.delete("/api/strategies/{strategy_id}", dependencies=[Depends(require_api_access)])
async def remove_strategy(strategy_id: str) -> dict[str, bool]:
    item = get_strategy(strategy_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    if item["active"]:
        raise HTTPException(status_code=409, detail="Deactivate the strategy before deleting it.")
    if not delete_strategy(strategy_id):
        raise HTTPException(status_code=409, detail="Strategy could not be deleted.")
    return {"deleted": True}


@app.post("/api/backtests/run", dependencies=[Depends(require_api_access)])
async def backtest(request: BacktestRequest) -> dict:
    try:
        return run_backtest(
            spec=request.spec, candles=request.candles, starting_cash=request.starting_cash,
            position_fraction=request.position_fraction, fee_bps=request.fee_bps,
            slippage_bps=request.slippage_bps,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/risk/check", dependencies=[Depends(require_api_access)])
async def risk_check(request: RiskCheckRequest) -> dict:
    return check_limit_order(
        symbol=request.symbol, side=request.side, quantity=request.quantity,
        limit_price=request.limit_price, account_equity=request.account_equity,
        daily_pnl_pct=request.daily_pnl_pct, reduce_only=request.reduce_only,
    ).as_dict()


@app.get("/api/brokers/alpaca/paper/account", dependencies=[Depends(require_api_access)])
async def alpaca_paper_account() -> dict:
    try:
        return await AlpacaPaperBroker().get_account()
    except BrokerConfigurationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BrokerRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/brokers/alpaca/paper/bars", dependencies=[Depends(require_api_access)])
async def alpaca_paper_bars(symbol: str = "SPY", timeframe: str = "1Day", limit: int = 100) -> list[dict]:
    from scalper.schemas import StrategySpec
    try:
        spec = StrategySpec(
            name="Read-only market bars", symbol=symbol.upper(), timeframe=timeframe,
            fast_ema=9, slow_ema=21,
        )
        return await AlpacaPaperBroker().get_bars(spec, limit=limit)
    except (BrokerConfigurationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BrokerRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/brokers/alpaca/paper/orders", dependencies=[Depends(require_api_access)])
async def alpaca_paper_order(request: PaperLimitOrderRequest) -> dict:
    try:
        broker = AlpacaPaperBroker()
        client_order_id = request.client_order_id

        existing = await broker.get_order_by_client_order_id(client_order_id)
        if existing:
            if not broker.order_matches(
                existing, symbol=request.symbol, side=request.side,
                quantity=request.quantity, limit_price=request.limit_price,
            ):
                raise HTTPException(status_code=409, detail="This client order id belongs to a different order.")
            return existing

        account = await broker.get_account()
        if account["trading_blocked"]:
            raise HTTPException(status_code=409, detail="Alpaca reports that trading is blocked.")
        equity = account["equity"]
        previous_equity = account["last_equity"]
        daily_pnl = ((equity / previous_equity) - 1) * 100 if previous_equity > 0 else 0.0
        reduce_only = False
        if request.side == "sell":
            position = await broker.get_position(request.symbol)
            if (
                not position
                or position["side"] != "long"
                or position["qty"] <= 0
                or request.quantity > position["qty"]
            ):
                raise HTTPException(status_code=422, detail="Sells may only reduce an existing long paper position.")
            reduce_only = True
        decision = check_limit_order(
            symbol=request.symbol, side=request.side, quantity=request.quantity,
            limit_price=request.limit_price, account_equity=equity,
            daily_pnl_pct=daily_pnl, reduce_only=reduce_only,
        )
        if not decision.approved:
            raise HTTPException(status_code=422, detail={"risk_rejected": list(decision.reasons)})
        return await broker.submit_limit_order(
            symbol=request.symbol, side=request.side, quantity=request.quantity,
            limit_price=request.limit_price, client_order_id=client_order_id,
        )
    except HTTPException:
        raise
    except BrokerConfigurationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BrokerOrderConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BrokerRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/manifest.webmanifest", include_in_schema=False)
async def manifest() -> FileResponse:
    return FileResponse(WEB_ROOT / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    return FileResponse(WEB_ROOT / "sw.js", media_type="application/javascript")


app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")
