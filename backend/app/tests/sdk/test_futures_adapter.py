import time
from decimal import Decimal
from uuid import uuid4

import pytest

from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction
from app.sdk.futures_adapter import FuturesTradingAdapter
from app.sdk.models import PlaceOrderRequest


def _sim_config():
    return {
        "mode": "real",
        "sdk_driver": "sim",
        "futures_account": "SIM_FUTURES_TEST",
    }


@pytest.fixture
def adapter():
    a = FuturesTradingAdapter(config=_sim_config())
    a.connect()
    yield a
    a.disconnect()


@pytest.mark.unit
def test_connect(adapter):
    status = adapter.connect()
    assert status.connected
    assert status.account_no == "SIM_FUTURES_TEST"


@pytest.mark.unit
def test_futures_positions(adapter):
    positions = adapter.get_positions()
    assert len(positions) >= 1
    assert positions[0].market == Market.FUTURES


@pytest.mark.unit
def test_futures_place_with_offset_metadata(adapter):
    events = []
    adapter.on_order_update(lambda e: events.append(e))
    req = PlaceOrderRequest(
        client_order_id="fut_close_today",
        account_id=uuid4(),
        market=Market.FUTURES,
        symbol="IF2509",
        side=OrderSide.SELL,
        action=SignalAction.CLOSE,
        price_type=PriceType.LIMIT,
        price=Decimal("3500"),
        quantity=Decimal("1"),
        metadata={"offset": "close_today", "hedge": "speculation"},
    )
    result = adapter.place_order(req)
    assert result.success
    assert result.sdk_order_id

    # 验证 driver 收到 OffsetFlag=CT
    raw = adapter._driver._orders[result.sdk_order_id]
    assert raw["OffsetFlag"] == "CT"
    assert raw["HedgeFlag"] == "S"

    time.sleep(0.4)
    assert any(e.status in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED} for e in events)
