from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction
from app.sdk.models import (
    AdapterStatus,
    CancelOrderRequest,
    KlineBar,
    OrderQuery,
    OrderSnapshot,
    PlaceOrderRequest,
    QuoteSnapshot,
    TradeQuery,
    TradeSnapshot,
)


@pytest.mark.unit
def test_quote_snapshot_decimal_serialization():
    snap = QuoteSnapshot(
        symbol="600000.SH",
        market=Market.STOCK,
        last_price=Decimal("10.15"),
        change_rate=Decimal("0.015"),
        volume=Decimal("100000"),
        bid_price=Decimal("10.14"),
        ask_price=Decimal("10.16"),
        quote_time=datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc),
    )
    data = snap.model_dump(mode="json")
    assert data["last_price"] == "10.15"
    assert data["change_rate"] == "0.015"
    assert data["volume"] == "100000"
    assert data["market"] == "stock"


@pytest.mark.unit
def test_kline_bar_decimal_serialization():
    bar = KlineBar(
        symbol="600000.SH",
        market=Market.STOCK,
        interval="1m",
        bar_time=datetime(2026, 7, 20, 9, 30, tzinfo=timezone.utc),
        open=Decimal("10.00"),
        high=Decimal("10.20"),
        low=Decimal("9.95"),
        close=Decimal("10.15"),
        volume=Decimal("100000"),
    )
    data = bar.model_dump(mode="json")
    assert data["open"] == "10.00"
    assert data["close"] == "10.15"
    assert data["interval"] == "1m"


@pytest.mark.unit
def test_place_order_request_fields():
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
    assert req.market == Market.STOCK
    assert req.quantity == Decimal("100")


@pytest.mark.unit
def test_adapter_status_model():
    status = AdapterStatus(connected=True, account_no="MOCK001", latency_ms=50)
    assert status.connected is True
    assert status.error_code is None


@pytest.mark.unit
def test_order_trade_snapshot_query_models():
    oq = OrderQuery(client_order_id="c1")
    tq = TradeQuery(sdk_trade_id="t1")
    snap = OrderSnapshot(
        client_order_id="c1",
        sdk_order_id="s1",
        status=OrderStatus.SUBMITTED,
        filled_quantity=Decimal("0"),
        remaining_quantity=Decimal("100"),
    )
    trade = TradeSnapshot(
        sdk_trade_id="t1",
        client_order_id="c1",
        symbol="600000.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        price=Decimal("10"),
        quantity=Decimal("100"),
        trade_time=datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc),
    )
    assert oq.client_order_id == "c1"
    assert tq.sdk_trade_id == "t1"
    assert snap.status == OrderStatus.SUBMITTED
    assert trade.quantity == Decimal("100")
