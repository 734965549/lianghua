"""strategy-runs API 与 unknown 订单确认 API 测试。"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.response import BizError
from app.db.models.order import Order
from app.db.models.system_event import SystemEvent
from app.main import app
from app.repositories.account_repo import AccountRepository
from app.repositories.strategy_repo import StrategyRunRepository
from app.schemas.enums import (
    Market,
    OrderSide,
    OrderStatus,
    PriceType,
    Severity,
    SignalAction,
    StrategyRunStatus,
    SystemStatus,
)
from app.services.risk_service import RiskService
from app.services.system_service import SystemStateService


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _create_unknown_order(db):
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    cid = f"unk_{uuid4().hex[:8]}"
    order = Order(
        client_order_id=cid,
        account_id=account.id,
        strategy_id="ma_cross",
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
        status=OrderStatus.UNKNOWN,
        submitted_at=datetime.now(timezone.utc),
        fail_reason="SDK status unmapped",
    )
    db.add(order)
    db.add(
        SystemEvent(
            module="order",
            event_code="ORDER_UNKNOWN",
            message=f"订单 {cid} 状态未知，需人工处理",
            severity=Severity.CRITICAL,
            resolved=False,
            payload={"client_order_id": cid},
            event_time=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return cid


def _cleanup(db, cid: str):
    db.query(SystemEvent).filter(SystemEvent.message.contains(cid)).delete(synchronize_session=False)
    db.query(Order).filter(Order.client_order_id == cid).delete(synchronize_session=False)
    db.commit()


@pytest.mark.integration
def test_list_strategy_runs(client, db):
    run_repo = StrategyRunRepository(db)
    run = run_repo.create_run(
        strategy_id="ma_cross",
        status=StrategyRunStatus.PENDING_CONFIRM,
        parameters={"symbols": ["600000.SH"]},
    )
    db.commit()

    resp = client.get("/api/strategy-runs?status=pending_confirm&page=1&page_size=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    ids = [item["run_id"] for item in body["data"]["items"]]
    assert str(run.id) in ids

    db.delete(run)
    db.commit()


@pytest.mark.integration
def test_confirm_unknown_order(client, db, reset_system_state):
    cid = _create_unknown_order(db)
    try:
        resp = client.post(
            f"/api/orders/{cid}/confirm-unknown",
            json={"confirm": True, "resolved_status": "cancelled", "reason": "已在券商端确认撤销"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "cancelled"

        order = db.query(Order).filter(Order.client_order_id == cid).first()
        assert order.status == OrderStatus.CANCELLED

        unresolved = (
            db.query(SystemEvent)
            .filter(SystemEvent.event_code == "ORDER_UNKNOWN", SystemEvent.resolved.is_(False))
            .filter(SystemEvent.message.contains(cid))
            .count()
        )
        assert unresolved == 0
    finally:
        _cleanup(db, cid)


@pytest.mark.integration
def test_resume_after_confirm_unknown(client, db, reset_system_state):
    from app.sdk import manager as sdk_manager
    from app.repositories.asset_repo import AssetRepository

    sdk_manager.ensure_connected()
    assets = AssetRepository(db)
    accounts = AccountRepository(db)
    for market in (Market.STOCK, Market.FUTURES):
        account = accounts.get_or_create_default(market)
        assets.insert_snapshot(
            account.id,
            sdk_manager.get_adapter_for_market(market).get_account(),
        )
    cid = _create_unknown_order(db)
    try:
        svc = SystemStateService(db, correlation_id="test_resume_after_confirm")
        svc.transition(SystemStatus.EMERGENCY_STOPPED, reason="test")
        db.commit()

        risk = RiskService(db, correlation_id="test_resume_after_confirm")
        with pytest.raises(BizError) as exc:
            risk.resume("尝试恢复")
        assert exc.value.code == "RISK_UNKNOWN_ORDERS_PENDING"

        client.post(
            f"/api/orders/{cid}/confirm-unknown",
            json={"confirm": True, "resolved_status": "cancelled", "reason": "test confirm"},
        )
        db.commit()

        result = risk.resume("已确认 unknown 订单")
        db.commit()
        assert result["status"] == "trading"
    finally:
        _cleanup(db, cid)


@pytest.mark.integration
def test_confirm_unknown_rejects_non_unknown(db, reset_system_state):
    from datetime import datetime, timezone
    from decimal import Decimal
    from uuid import uuid4

    from app.repositories.account_repo import AccountRepository
    from app.repositories.order_repo import OrderRepository
    from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction
    from app.services.order_service import OrderService

    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    cid = f"notunk_{uuid4().hex[:8]}"
    OrderRepository(db).create_order(
        client_order_id=cid,
        account_id=account.id,
        strategy_id="ma_cross",
        signal_id=None,
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
        status=OrderStatus.SUBMITTED,
        submitted_at=datetime.now(timezone.utc),
    )
    db.commit()
    svc = OrderService()
    with pytest.raises(BizError) as exc:
        svc.confirm_unknown(db, cid, resolved_status=OrderStatus.CANCELLED, correlation_id="t")
    assert exc.value.code == "ORDER_NOT_UNKNOWN"
    db.query(Order).filter(Order.client_order_id == cid).delete(synchronize_session=False)
    db.commit()


@pytest.mark.integration
def test_confirm_unknown_requires_confirm_flag(client, db, reset_system_state):
    cid = _create_unknown_order(db)
    try:
        resp = client.post(
            f"/api/orders/{cid}/confirm-unknown",
            json={"confirm": False, "resolved_status": "cancelled"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "ORDER_CONFIRM_REQUIRED"
    finally:
        _cleanup(db, cid)
