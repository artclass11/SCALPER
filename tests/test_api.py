from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from scalper.api import app


def test_health_is_public_but_headers_are_hardened(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_local_ui_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "SCALPER" in response.text
    assert "Strategy Workbench" in response.text
    assert "Unlock API" in response.text


def test_remote_api_requires_bearer_token(client, monkeypatch):
    monkeypatch.delenv("SCALPER_TEST_MODE", raising=False)
    monkeypatch.delenv("SCALPER_API_TOKEN", raising=False)
    assert client.get("/api/status").status_code == 403
    monkeypatch.setenv("SCALPER_API_TOKEN", "unit-test-token")
    assert client.get("/api/status").status_code == 401
    response = client.get("/api/status", headers={"Authorization": "Bearer unit-test-token"})
    assert response.status_code == 200


def test_reverse_proxy_loopback_source_does_not_bypass_auth(client, monkeypatch):
    monkeypatch.delenv("SCALPER_TEST_MODE", raising=False)
    monkeypatch.delenv("SCALPER_API_TOKEN", raising=False)
    with TestClient(app, client=("127.0.0.1", 9000)) as proxied:
        assert proxied.get("/api/status", headers={"Host": "scalper.example.com"}).status_code == 403
        monkeypatch.setenv("SCALPER_API_TOKEN", "long-enough-unit-test-token-123456")
        assert proxied.get("/api/status", headers={"Host": "localhost:8000"}).status_code == 401
        response = proxied.get("/api/status", headers={
            "Host": "localhost:8000",
            "Authorization": "Bearer long-enough-unit-test-token-123456",
        })
        assert response.status_code == 200


def test_parse_endpoint_returns_validated_spec(client):
    response = client.post("/api/strategies/parse", json={"prompt": "EMA 9 above EMA 21 on SPY, 5 minute bars"})
    assert response.status_code == 200
    assert response.json()["fast_ema"] == 9
    assert response.json()["symbol"] == "SPY"


def test_parse_rejects_arbitrary_code(client):
    response = client.post("/api/strategies/parse", json={"prompt": "run python import os and delete files"})
    assert response.status_code == 422


def test_saved_strategies_start_inactive(client):
    spec = {"name": "EMA 9/21 crossover on SPY", "description": "test", "symbol": "SPY",
            "timeframe": "1Day", "fast_ema": 9, "slow_ema": 21, "strategy_type": "ema_crossover"}
    created = client.post("/api/strategies", json={"name": "Review first", "spec": spec})
    assert created.status_code == 200
    assert created.json()["active"] is False
    assert client.get("/api/strategies").json()[0]["name"] == "Review first"


def test_activation_fails_closed_when_automation_disabled(client):
    spec = {"name": "EMA 9/21 crossover on SPY", "symbol": "SPY", "fast_ema": 9, "slow_ema": 21}
    created = client.post("/api/strategies", json={"name": "Inactive", "spec": spec}).json()
    response = client.post(f"/api/strategies/{created['id']}/activate", json={"confirmed": True})
    assert response.status_code == 409


def test_backtest_endpoint(client):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = []
    for index, close in enumerate([10, 9, 8, 7, 8, 9, 11, 12, 10, 8, 7, 6]):
        candles.append({"timestamp": (start + timedelta(days=index)).isoformat(), "open": close,
                        "high": close + 0.5, "low": close - 0.5, "close": close, "volume": 1000})
    spec = {"name": "Test EMA 2/4", "symbol": "SPY", "timeframe": "1Day",
            "fast_ema": 2, "slow_ema": 4, "strategy_type": "ema_crossover"}
    response = client.post("/api/backtests/run", json={"spec": spec, "candles": candles})
    assert response.status_code == 200
    assert response.json()["trade_count"] >= 1


def test_paper_sell_cannot_add_to_existing_short_position(client, monkeypatch):
    monkeypatch.setenv("SCALPER_ALPACA_PAPER_KEY", "paper-key")
    monkeypatch.setenv("SCALPER_ALPACA_PAPER_SECRET", "paper-secret")

    class FakeBroker:
        def __init__(self): pass
        async def get_order_by_client_order_id(self, client_order_id): return None
        async def get_account(self):
            return {"status": "ACTIVE", "equity": 10000.0, "last_equity": 10000.0,
                    "buying_power": 10000.0, "trading_blocked": False}
        async def get_position(self, symbol):
            return {"symbol": symbol, "qty": 2.0, "side": "short", "market_value": -200.0}
        async def submit_limit_order(self, **kwargs): raise AssertionError("Must not submit a short-increasing sell.")

    monkeypatch.setattr("scalper.api.AlpacaPaperBroker", FakeBroker)
    response = client.post("/api/brokers/alpaca/paper/orders", json={
        "symbol": "SPY", "side": "sell", "quantity": 1, "limit_price": 100,
        "confirmed": True, "client_order_id": "scalper-test-order-1",
    })
    assert response.status_code == 422


def test_existing_idempotency_key_returns_same_order_before_risk_checks(client, monkeypatch):
    monkeypatch.setenv("SCALPER_ALPACA_PAPER_KEY", "paper-key")
    monkeypatch.setenv("SCALPER_ALPACA_PAPER_SECRET", "paper-secret")
    order = {"id": "existing-id", "client_order_id": "scalper-test-order-2", "symbol": "SPY",
             "side": "buy", "qty": "1", "limit_price": "100", "status": "accepted"}

    class FakeBroker:
        def __init__(self): pass
        async def get_order_by_client_order_id(self, client_order_id): return order
        @staticmethod
        def order_matches(existing, **kwargs):
            return existing["symbol"] == kwargs["symbol"] and existing["side"] == kwargs["side"]
        async def get_account(self): raise AssertionError("Existing order should be reconciled first.")
        async def submit_limit_order(self, **kwargs): raise AssertionError("Must not duplicate an order.")

    monkeypatch.setattr("scalper.api.AlpacaPaperBroker", FakeBroker)
    response = client.post("/api/brokers/alpaca/paper/orders", json={
        "symbol": "SPY", "side": "buy", "quantity": 1, "limit_price": 100,
        "confirmed": True, "client_order_id": "scalper-test-order-2",
    })
    assert response.status_code == 200
    assert response.json()["id"] == "existing-id"
