import time
from decimal import Decimal
from uuid import uuid4

import pytest

from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction
from app.sdk.base import SDKNotConfigured, SDKOrderRejected
from app.sdk.mapping import map_ths_order_status
from app.sdk.stock_adapter import StockTradingAdapter
from app.sdk.models import CancelOrderRequest, PlaceOrderRequest


def _sim_config(**overrides):
    base = {
        "mode": "real",
        "sdk_driver": "sim",
        "stock_account": "SIM_STOCK_TEST",
        "futures_account": "SIM_FUTURES_TEST",
    }
    base.update(overrides)
    return base


@pytest.fixture
def adapter():
    a = StockTradingAdapter(config=_sim_config())
    a.connect()
    yield a
    a.disconnect()


@pytest.mark.unit
def test_connect(adapter):
    status = adapter.connect()
    assert status.connected is True
    assert status.account_no == "SIM_STOCK_TEST"


@pytest.mark.unit
def test_get_account_and_positions(adapter):
    account = adapter.get_account()
    assert account.total_asset == Decimal("1000000")
    positions = adapter.get_positions()
    assert len(positions) >= 1
    assert positions[0].symbol == "600000.SH"


@pytest.mark.unit
def test_subscribe_receives_quotes(adapter):
    received = []
    adapter.on_quote_update(lambda q: received.append(q))
    adapter.subscribe_quotes(["600000.SH"])
    time.sleep(1.2)
    assert len(received) >= 1
    assert received[0].symbol == "600000.SH"


@pytest.mark.unit
def test_place_order_and_local_mapping(adapter):
    events = []
    adapter.on_order_update(lambda e: events.append(e))
    req = PlaceOrderRequest(
        client_order_id="stock_test_1",
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
    assert result.sdk_order_id
    assert result.status == OrderStatus.SUBMITTED

    time.sleep(0.5)
    assert len(events) >= 1
    # 适配层通过 sdk_order_id 回查本地映射，补全 client_order_id
    assert events[0].client_order_id == "stock_test_1"
    assert events[0].sdk_order_id == result.sdk_order_id

    polled = adapter.query_orders({})
    row = next(r for r in polled if r["client_order_id"] == "stock_test_1")
    assert row["sdk_order_id"] == result.sdk_order_id


@pytest.mark.unit
def test_cancel_order(adapter):
    req = PlaceOrderRequest(
        client_order_id="stock_cancel",
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
    )
    placed = adapter.place_order(req)
    cancel = adapter.cancel_order(
        CancelOrderRequest(
            client_order_id=req.client_order_id,
            sdk_order_id=placed.sdk_order_id,
            market=Market.STOCK,
        )
    )
    assert cancel.success
    assert cancel.status == OrderStatus.CANCELLED


@pytest.mark.unit
def test_unknown_status_mapping():
    assert map_ths_order_status("9") is None
    assert map_ths_order_status("0") == OrderStatus.SUBMITTED


@pytest.mark.unit
def test_unconfigured_driver_raises():
    adapter = StockTradingAdapter(
        config={"mode": "real", "sdk_driver": "auto", "stock_sdk_path": "", "stock_account": ""}
    )
    with pytest.raises(SDKNotConfigured):
        adapter.connect()


@pytest.mark.unit
def test_inject_fail():
    adapter = StockTradingAdapter(config=_sim_config())
    adapter.connect()
    adapter._driver.inject_next_order_fail()
    req = PlaceOrderRequest(
        client_order_id="fail_1",
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
    adapter.disconnect()
