import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.api.response import BizError
from app.db.models.order import Order
from app.repositories.account_repo import AccountRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.trade_repo import TradeRepository
from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction, SystemStatus
from app.sdk import manager as sdk_manager
from app.sdk.models import PlaceOrderRequest
from app.services.order_service import OrderService, order_service
from app.services.system_service import SystemStateService
from app.services.trade_service import trade_service


def _make_signal_row(*, strategy_id: str = "test_order_flow", symbol: str = "600000.SH"):
    from app.db.models.strategy_signal import StrategySignal

    signal_id = uuid4()
    now = datetime.now(timezone.utc)
    return StrategySignal(
        signal_id=signal_id,
        strategy_id=strategy_id,
        symbol=symbol,
        market=Market.STOCK,
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
        reason="test",
        signal_time=now,
    )


def _make_place_req(client_order_id: str) -> PlaceOrderRequest:
    return PlaceOrderRequest(
        client_order_id=client_order_id,
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
    )


@pytest.mark.unit
def test_order_state_machine_valid():
    svc = OrderService()
    order = Order(status=OrderStatus.PENDING_RISK, client_order_id="t1")
    svc.transition(order, OrderStatus.SUBMITTING)
    assert order.status == OrderStatus.SUBMITTING

    order.status = OrderStatus.SUBMITTING
    svc.transition(order, OrderStatus.SUBMITTED)
    assert order.status == OrderStatus.SUBMITTED

    order.status = OrderStatus.SUBMITTED
    svc.transition(order, OrderStatus.PARTIALLY_FILLED)
    order.status = OrderStatus.PARTIALLY_FILLED
    svc.transition(order, OrderStatus.FILLED)
    assert order.status == OrderStatus.FILLED


@pytest.mark.unit
def test_order_state_machine_invalid():
    svc = OrderService()
    order = Order(status=OrderStatus.SUBMITTED, client_order_id="t2")
    with pytest.raises(BizError) as exc:
        svc.transition(order, OrderStatus.SUBMITTING)
    assert exc.value.code == "ORDER_INVALID_TRANSITION"


@pytest.mark.integration
def test_create_submit_filled(db, reset_system_state, monkeypatch):
    svc_state = SystemStateService(db, correlation_id="test_order_flow")
    svc_state.transition(SystemStatus.TRADING, reason="test")
    db.commit()

    AccountRepository(db).get_or_create_default(Market.STOCK)
    db.commit()

    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    adapter = sdk_manager.get_stock_adapter()
    from app.services.order_service import order_service as osvc
    from app.services.trade_service import trade_service as tsvc

    adapter.on_order_update(osvc.on_order_update)
    adapter.on_trade_update(tsvc.on_trade_update)

    sig = _make_signal_row()
    db.add(sig)
    db.flush()

    client_order_id = f"lh_{sig.signal_time:%Y%m%d}_{sig.signal_id.hex[:8]}"
    place_req = _make_place_req(client_order_id)

    order = order_service.create_from_signal(db, sig, place_req, correlation_id="test_flow")
    assert order.client_order_id == client_order_id

    deadline = time.time() + 3.0
    final_status = None
    while time.time() < deadline:
        db.expire_all()
        row = OrderRepository(db).get_by_client_order_id(client_order_id)
        if row and row.status == OrderStatus.FILLED:
            final_status = row.status
            break
        time.sleep(0.1)

    assert final_status == OrderStatus.FILLED
    trades, total = TradeRepository(db).list_trades(client_order_id=client_order_id, limit=10)
    assert total >= 1
    filled_sum = sum(Decimal(str(t.quantity)) for t in trades)
    assert filled_sum == Decimal("100")

    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_submit_failed(db, reset_system_state):
    AccountRepository(db).get_or_create_default(Market.STOCK)
    db.commit()

    sdk_manager.reset_adapters()
    sdk_manager.ensure_connected()
    adapter = sdk_manager.get_stock_adapter()
    adapter.inject_next_order_fail()

    from app.services.order_service import order_service as osvc
    from app.services.trade_service import trade_service as tsvc

    adapter.on_order_update(osvc.on_order_update)
    adapter.on_trade_update(tsvc.on_trade_update)

    now = datetime.now(timezone.utc)
    order_repo = OrderRepository(db)
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    order = order_repo.create_order(
        client_order_id=f"lh_{now:%Y%m%d}_{uuid4().hex[:8]}",
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
        status=OrderStatus.SUBMITTING,
        submitted_at=now,
    )
    db.commit()

    result = trade_service.submit(order.id, correlation_id="test_fail")
    assert result.status == OrderStatus.FAILED
    assert result.fail_reason

    sdk_manager.reset_adapters()


@pytest.mark.integration
def test_confirm_unknown_order(db, reset_system_state):
    now = datetime.now(timezone.utc)
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    cid = f"unk_svc_{uuid4().hex[:8]}"
    order_repo = OrderRepository(db)
    order_repo.create_order(
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
        status=OrderStatus.UNKNOWN,
        submitted_at=now,
    )
    db.commit()

    svc = OrderService()
    row = svc.confirm_unknown(
        db,
        cid,
        resolved_status=OrderStatus.CANCELLED,
        reason="测试确认",
        correlation_id="test_confirm_unknown",
    )
    db.commit()
    assert row.status == OrderStatus.CANCELLED
    assert "测试确认" in row.fail_reason

    db.query(Order).filter(Order.client_order_id == cid).delete(synchronize_session=False)
    db.commit()
