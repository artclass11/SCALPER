import math

from scalper.risk import check_limit_order


def test_order_under_limits_is_approved(monkeypatch):
    monkeypatch.setenv("SCALPER_MAX_ORDER_NOTIONAL", "2500")
    monkeypatch.setenv("SCALPER_MAX_POSITION_PCT", "5")
    result = check_limit_order(symbol="SPY", side="buy", quantity=1, limit_price=100,
                               account_equity=10000, daily_pnl_pct=0, kill_switch=False)
    assert result.approved
    assert result.order_notional == 100


def test_rejects_order_above_notional_cap(monkeypatch):
    monkeypatch.setenv("SCALPER_MAX_ORDER_NOTIONAL", "250")
    result = check_limit_order(symbol="SPY", side="buy", quantity=10, limit_price=100,
                               account_equity=100000, daily_pnl_pct=0, kill_switch=False)
    assert not result.approved
    assert "order_exceeds_permitted_notional" in result.reasons


def test_kill_switch_blocks_new_risk_but_allows_reduce_only():
    blocked = check_limit_order(symbol="SPY", side="buy", quantity=1, limit_price=100,
                                account_equity=10000, kill_switch=True)
    exit_order = check_limit_order(symbol="SPY", side="sell", quantity=10, limit_price=100,
                                   account_equity=10000, kill_switch=True, reduce_only=True)
    assert not blocked.approved
    assert "kill_switch_enabled" in blocked.reasons
    assert exit_order.approved


def test_rejects_daily_loss_limit():
    result = check_limit_order(symbol="SPY", side="buy", quantity=1, limit_price=100,
                               account_equity=10000, daily_pnl_pct=-3, kill_switch=False)
    assert not result.approved
    assert "daily_loss_limit_reached" in result.reasons


def test_rejects_nan_without_returning_nan_metrics():
    result = check_limit_order(symbol="SPY", side="buy", quantity=float("nan"), limit_price=100,
                               account_equity=10000, kill_switch=False)
    assert not result.approved
    assert "non_finite_numeric_input" in result.reasons
    assert math.isfinite(result.order_notional)
    assert math.isfinite(result.permitted_notional)
