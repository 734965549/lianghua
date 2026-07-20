"""双通道幂等：回调 + 轮询不应导致重复状态异常。"""

import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.models.order import Order
from app.repositories.account_repo import AccountRepository
from app.repositories.order_repo import OrderRepository
from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction
from app.sdk.stock_adapter import StockTradingAdapter
from app.sdk.models import OrderUpdateEvent, PlaceOrderRequest
from app.services.order_service import order_service
from app.workers.sync_jobs import sync_orders_trades


def _sim_adapter():
    return StockTradingAdapter(
        config={
            "mode": "real",
            "sdk_driver": "sim",
            "stock_account": "SIM_DUAL",
        }
    )


@pytest.mark.unit
def test_callback_then_poll_same_status(db, monkeypatch):
    """先回调更新，再轮询相同状态：订单保持终态且不抛错。"""
    adapter = _sim_adapter()
    adapter.connect()

    client_order_id = f"dual_{uuid4().hex[:8]}"
    repo = OrderRepository(db)
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    order = Order(
        client_order_id=client_order_id,
        account_id=account.id,
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
        status=OrderStatus.SUBMITTED,
        filled_quantity=Decimal("0"),
        created_at=datetime.now(timezone.utc),
        last_event_at=datetime.now(timezone.utc),
    )
    db.add(order)
    db.commit()

    # 先通过适配器下单建立映射
    req = PlaceOrderRequest(
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
    result = adapter.place_order(req)
    order.sdk_order_id = result.sdk_order_id
    db.commit()

    # 通道1：回调（无 client_order_id，靠 sdk_order_id 回查）
    order_service.on_order_update(
        OrderUpdateEvent(
            client_order_id=None,
            sdk_order_id=result.sdk_order_id,
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("100"),
            remaining_quantity=Decimal("0"),
            event_time=datetime.now(timezone.utc),
        )
    )
    db.refresh(order)
    assert order.status == OrderStatus.FILLED

    # 通道2：轮询相同 FILLED
    from app.sdk import manager as sdk_manager
    from app.services.market_service import market_service

    monkeypatch.setattr(sdk_manager, "get_adapter_for_market", lambda m: adapter)
    monkeypatch.setattr(market_service, "_started", True)
    sync_orders_trades(db)
    db.refresh(order)
    assert order.status == OrderStatus.FILLED
    assert Decimal(str(order.filled_quantity)) == Decimal("100")

    adapter.disconnect()


@pytest.mark.unit
def test_poll_unknown_status_marks_unknown(db, monkeypatch):
    adapter = _sim_adapter()
    adapter.connect()

    client_order_id = f"unk_{uuid4().hex[:8]}"
    account = AccountRepository(db).get_or_create_default(Market.STOCK)
    order = Order(
        client_order_id=client_order_id,
        account_id=account.id,
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
        status=OrderStatus.SUBMITTED,
        filled_quantity=Decimal("0"),
        created_at=datetime.now(timezone.utc),
        last_event_at=datetime.now(timezone.utc),
    )
    db.add(order)
    db.commit()

    req = PlaceOrderRequest(
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
    result = adapter.place_order(req)
    order.sdk_order_id = result.sdk_order_id
    db.commit()

    adapter._driver.set_order_unknown_status(result.sdk_order_id, "9")
    from app.sdk import manager as sdk_manager
    from app.services.market_service import market_service

    monkeypatch.setattr(sdk_manager, "get_adapter_for_market", lambda m: adapter)
    monkeypatch.setattr(market_service, "_started", True)
    sync_orders_trades(db)
    db.refresh(order)
    assert order.status == OrderStatus.UNKNOWN

    adapter.disconnect()
