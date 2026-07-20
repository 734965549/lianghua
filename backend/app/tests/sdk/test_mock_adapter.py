import time
from decimal import Decimal
from uuid import uuid4

import pytest

from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction
from app.sdk.base import SDKDisconnected, SDKOrderRejected
from app.sdk.mock_adapter import MockTradingAdapter
from app.sdk.models import CancelOrderRequest, PlaceOrderRequest


@pytest.fixture
def adapter():
    a = MockTradingAdapter(market=Market.STOCK)
    a.connect()
    yield a
    a.disconnect()


@pytest.mark.unit
def test_connect(adapter):
    status = adapter.connect()
    assert status.connected is True
    assert status.account_no == "MOCK_STOCK"


@pytest.mark.unit
def test_subscribe_receives_quotes(adapter):
    received = []
    adapter.on_quote_update(lambda q: received.append(q))
    adapter.subscribe_quotes(["600000.SH"])
    time.sleep(1.2)
    assert len(received) >= 1
    assert received[0].symbol == "600000.SH"
    assert isinstance(received[0].last_price, Decimal)


@pytest.mark.unit
def test_place_order_success(adapter):
    events = []
    adapter.on_order_update(lambda e: events.append(("order", e)))
    adapter.on_trade_update(lambda e: events.append(("trade", e)))

    req = PlaceOrderRequest(
        client_order_id="test_1",
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
    assert result.success
    assert result.status == OrderStatus.SUBMITTED

    time.sleep(0.6)
    statuses = [e[1].status for e in events if e[0] == "order"]
    assert OrderStatus.PARTIALLY_FILLED in statuses
    assert OrderStatus.FILLED in statuses
    trades = [e[1] for e in events if e[0] == "trade"]
    assert len(trades) == 2
    assert sum(t.quantity for t in trades) == Decimal("100")


@pytest.mark.unit
def test_inject_fail(adapter):
    adapter.inject_next_order_fail()
    req = PlaceOrderRequest(
        client_order_id="test_fail",
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
    )
    with pytest.raises(SDKOrderRejected):
        adapter.place_order(req)


@pytest.mark.unit
def test_cancel_order(adapter):
    req = PlaceOrderRequest(
        client_order_id="test_cancel",
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
    cancel = adapter.cancel_order(
        CancelOrderRequest(
            client_order_id=req.client_order_id,
            sdk_order_id=result.sdk_order_id,
            market=Market.STOCK,
        )
    )
    assert cancel.success
    assert cancel.status == OrderStatus.CANCELLED


@pytest.mark.unit
def test_inject_disconnect():
    a = MockTradingAdapter(market=Market.STOCK)
    a.inject_disconnect()
    with pytest.raises(SDKDisconnected):
        a.connect()


@pytest.mark.unit
def test_disconnect_stops_quotes(adapter):
    adapter.subscribe_quotes(["600000.SH"])
    adapter.disconnect()
    assert adapter._connected is False


@pytest.mark.unit
def test_stop_quotes(adapter):
    received = []
    adapter.on_quote_update(lambda q: received.append(q))
    adapter.subscribe_quotes(["600000.SH"])
    time.sleep(0.6)
    count_before = len(received)
    adapter.stop_quotes()
    time.sleep(0.6)
    assert len(received) == count_before
