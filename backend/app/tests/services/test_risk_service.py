from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.schemas.enums import Market, OrderSide, PriceType, SignalAction, SystemStatus
from app.sdk.models import PlaceOrderRequest
from app.services.risk_service import RiskService, ZERO_ACCOUNT_ID
from app.services.system_service import SystemStateService


def _make_request(
    *,
    symbol: str = "600000.SH",
    strategy_id: str = "ma_cross",
    side: OrderSide = OrderSide.BUY,
    action: SignalAction = SignalAction.OPEN,
) -> PlaceOrderRequest:
    return PlaceOrderRequest(
        client_order_id=f"test_{uuid4().hex[:8]}",
        account_id=ZERO_ACCOUNT_ID,
        market=Market.STOCK,
        symbol=symbol,
        side=side,
        action=action,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
        metadata={"strategy_id": strategy_id},
    )


@pytest.mark.integration
def test_blacklist_rejects(db, reset_system_state):
    from app.repositories.risk_repo import RiskRepository

    RiskRepository(db).update_config({"allowed_symbols": []})
    db.commit()

    svc = SystemStateService(db, correlation_id="test_blacklist")
    svc.transition(SystemStatus.TRADING, reason="test")
    db.commit()

    risk = RiskService(db, correlation_id="test_blacklist")
    passed, results, check_id = risk.check(_make_request(symbol="ST001.SH"))
    db.commit()

    assert passed is False
    assert check_id is not None
    assert any(r.rule_code == "RISK_SYMBOL_BLACKLIST" for r in results)


@pytest.mark.integration
def test_non_trading_state_rejects(db, reset_system_state):
    risk = RiskService(db, correlation_id="test_state")
    passed, results, _ = risk.check(_make_request())
    db.commit()

    assert passed is False
    assert any(r.rule_code == "RISK_SYSTEM_STATE" for r in results)


@pytest.mark.integration
def test_whitelist_passes_when_trading(db, reset_system_state):
    svc = SystemStateService(db, correlation_id="test_whitelist")
    svc.transition(SystemStatus.TRADING, reason="test")
    db.commit()

    risk = RiskService(db, correlation_id="test_whitelist")
    passed, results, check_id = risk.check(_make_request(symbol="600000.SH"))
    db.commit()

    assert passed is True
    assert check_id is not None
    assert all(r.result != "rejected" for r in results)


@pytest.mark.integration
def test_risk_never_calls_place_order(db, reset_system_state, monkeypatch):
    from app.sdk import manager as sdk_manager

    called = {"count": 0}

    def fake_place_order(*args, **kwargs):
        called["count"] += 1
        raise AssertionError("place_order should not be called in phase 3")

    stock = sdk_manager.get_stock_adapter()
    monkeypatch.setattr(stock, "place_order", fake_place_order)

    svc = SystemStateService(db, correlation_id="test_spy")
    svc.transition(SystemStatus.TRADING, reason="test")
    db.commit()

    risk = RiskService(db, correlation_id="test_spy")
    risk.check(_make_request(symbol="ST001.SH"))
    risk.check(_make_request(symbol="600000.SH"))
    db.commit()

    assert called["count"] == 0


@pytest.mark.integration
def test_emergency_stopped_rejects(db, reset_system_state):
    svc = SystemStateService(db, correlation_id="test_emergency")
    svc.transition(SystemStatus.EMERGENCY_STOPPED, reason="stop")
    db.commit()

    risk = RiskService(db, correlation_id="test_emergency")
    passed, results, _ = risk.check(_make_request())
    db.commit()

    assert passed is False
    assert any(r.rule_code == "RISK_SYSTEM_STATE" for r in results)


@pytest.mark.integration
def test_duplicate_signal_compares_action(db, reset_system_state):
    """同策略同标的同 side 但不同 action 不应被判为重复。"""
    from app.repositories.signal_repo import SignalRepository

    svc = SystemStateService(db, correlation_id="test_dup")
    svc.transition(SystemStatus.TRADING, reason="test")
    db.commit()

    SignalRepository(db).add_signal(
        signal_id=uuid4(),
        strategy_id="ma_cross",
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
        reason="prior open",
        signal_time=datetime.now(timezone.utc),
    )
    db.commit()

    risk = RiskService(db, correlation_id="test_dup")
    # 同 side 不同 action → 应通过
    passed_close, results_close, _ = risk.check(
        _make_request(side=OrderSide.BUY, action=SignalAction.CLOSE)
    )
    db.commit()
    assert passed_close is True
    assert all(r.rule_code != "RISK_DUPLICATE_SIGNAL" or r.result != "rejected" for r in results_close)

    # 同 side 同 action → 应拒绝
    passed_open, results_open, _ = risk.check(
        _make_request(side=OrderSide.BUY, action=SignalAction.OPEN)
    )
    db.commit()
    assert passed_open is False
    assert any(r.rule_code == "RISK_DUPLICATE_SIGNAL" for r in results_open)
