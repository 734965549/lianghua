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
    assert all(t.price <= req.price for t in trades)


@pytest.mark.unit
def test_sell_limit_never_fills_below_limit(adapter):
    trades = []
    adapter.on_trade_update(trades.append)
    req = PlaceOrderRequest(
        client_order_id="sell_limit",
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="000001.SZ",
        side=OrderSide.SELL,
        action=SignalAction.CLOSE,
        price_type=PriceType.LIMIT,
        price=Decimal("11.47"),
        quantity=Decimal("100"),
    )

    assert adapter.place_order(req).success
    time.sleep(0.6)

    assert len(trades) == 2
    assert all(trade.price >= req.price for trade in trades)


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


@pytest.mark.unit
def test_connection_change_callbacks():
    events = []
    a = MockTradingAdapter(market=Market.STOCK)
    a.on_connection_change(lambda e: events.append(e))
    a.connect()
    a.disconnect()
    assert len(events) >= 2
    assert events[0].connected is True
    assert events[-1].connected is False


@pytest.mark.unit
def test_subscribe_requires_connect():
    a = MockTradingAdapter(market=Market.STOCK)
    with pytest.raises(SDKDisconnected):
        a.subscribe_quotes(["600000.SH"])


@pytest.mark.unit
def test_get_quote_paths(adapter):
    snap = adapter.get_quote("600000.SH")
    assert snap.last_price == Decimal("10.00")
    adapter.subscribe_quotes(["600000.SH"])
    time.sleep(0.7)
    cached = adapter.get_quote("600000.SH")
    assert cached.symbol == "600000.SH"

    a = MockTradingAdapter(market=Market.STOCK)
    with pytest.raises(SDKDisconnected):
        a.get_quote("600000.SH")


@pytest.mark.unit
def test_get_kline_and_account_disconnected():
    a = MockTradingAdapter(market=Market.STOCK)
    with pytest.raises(SDKDisconnected):
        a.get_kline("600000.SH", "1m", None, None)
    with pytest.raises(SDKDisconnected):
        a.get_account()


@pytest.mark.unit
def test_get_account_and_positions(adapter):
    acc = adapter.get_account()
    assert acc.available_cash > 0
    assert adapter.get_positions() == []


@pytest.mark.unit
def test_place_order_disconnected():
    a = MockTradingAdapter(market=Market.STOCK)
    with pytest.raises(SDKDisconnected):
        a.place_order(
            PlaceOrderRequest(
                client_order_id="x",
                account_id=uuid4(),
                market=Market.STOCK,
                symbol="600000.SH",
                side=OrderSide.BUY,
                action=SignalAction.OPEN,
                price_type=PriceType.LIMIT,
                price=Decimal("10"),
                quantity=Decimal("100"),
            )
        )


@pytest.mark.unit
def test_place_order_qty_one_full_fill_branch(adapter):
    """quantity=1 时 partial 量化为 0，走整笔一次成交分支。"""
    events = []
    adapter.on_order_update(lambda e: events.append(e))
    adapter.on_trade_update(lambda e: events.append(e))
    req = PlaceOrderRequest(
        client_order_id="qty1",
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("1"),
    )
    assert adapter.place_order(req).success
    time.sleep(0.5)
    statuses = [e.status for e in events if hasattr(e, "status")]
    assert OrderStatus.FILLED in statuses


@pytest.mark.unit
def test_cancel_disconnected_and_missing(adapter):
    a = MockTradingAdapter(market=Market.STOCK)
    with pytest.raises(SDKDisconnected):
        a.cancel_order(
            CancelOrderRequest(client_order_id="x", market=Market.STOCK)
        )
    with pytest.raises(SDKOrderRejected):
        adapter.cancel_order(
            CancelOrderRequest(client_order_id="missing", market=Market.STOCK)
        )


@pytest.mark.unit
def test_query_trades_filters(adapter):
    req = PlaceOrderRequest(
        client_order_id="qtr",
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
    time.sleep(0.6)
    by_cid = adapter.query_trades({"client_order_id": "qtr"})
    assert len(by_cid) >= 1
    by_sdk = adapter.query_trades({"sdk_order_id": result.sdk_order_id})
    assert len(by_sdk) >= 1
    by_sym = adapter.query_trades({"symbol": "600000.SH"})
    assert len(by_sym) >= 1
    tid = by_cid[0].sdk_trade_id
    by_tid = adapter.query_trades({"sdk_trade_id": tid})
    assert len(by_tid) == 1


@pytest.mark.unit
def test_inject_unknown_status(adapter):
    req = PlaceOrderRequest(
        client_order_id="unk_st",
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
    )
    adapter.place_order(req)
    adapter.inject_unknown_status("unk_st", "SDK_STATUS_XYZ")
    assert adapter._orders["unk_st"]["status"] == "SDK_STATUS_XYZ"


@pytest.mark.unit
def test_inject_unknown_status_missing_order_noop(adapter):
    """订单不存在时 inject_unknown_status 应为无操作。"""
    adapter.inject_unknown_status("no_such_cid", "SDK_STATUS_XYZ")
    assert "no_such_cid" not in adapter._orders


@pytest.mark.unit
def test_clear_inject_disconnect(adapter):
    adapter.inject_disconnect()
    with pytest.raises(SDKDisconnected):
        adapter.connect()
    adapter.clear_inject_disconnect()
    status = adapter.connect()
    assert status.connected is True


@pytest.mark.unit
def test_get_kline_intervals(adapter):
    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=15)
    bars_1m = adapter.get_kline("600000.SH", "1m", start, end)
    assert len(bars_1m) >= 1
    bars_5m = adapter.get_kline("600000.SH", "5m", start, end)
    assert len(bars_5m) >= 1
    bars_1d = adapter.get_kline("600000.SH", "1d", end - timedelta(days=3), end)
    assert len(bars_1d) >= 1
    # 未知 interval 回退到 1m
    bars_fallback = adapter.get_kline("600000.SH", "unknown", start, end)
    assert len(bars_fallback) == len(bars_1m)


@pytest.mark.unit
def test_query_orders_returns_snapshots(adapter):
    req = PlaceOrderRequest(
        client_order_id="qo_1",
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("10"),
        quantity=Decimal("100"),
    )
    adapter.place_order(req)
    rows = adapter.query_orders()
    assert any(r.client_order_id == "qo_1" for r in rows)


@pytest.mark.unit
def test_emit_trade_dedup(adapter, monkeypatch):
    monkeypatch.setattr("app.sdk.mock_adapter.time.time", lambda: 12345.0)
    monkeypatch.setattr("app.sdk.mock_adapter.random.randint", lambda a, b: 7777)
    adapter._emit_trade(
        "sdk1", "c1", Decimal("10"), Decimal("10"), "600000.SH", OrderSide.BUY
    )
    n1 = len(adapter._trades)
    adapter._emit_trade(
        "sdk1", "c1", Decimal("10"), Decimal("10"), "600000.SH", OrderSide.BUY
    )
    assert len(adapter._trades) == n1


@pytest.mark.unit
def test_futures_default_quote_price():
    a = MockTradingAdapter(market=Market.FUTURES)
    a.connect()
    try:
        snap = a.get_quote("IF2509")
        assert snap.last_price == Decimal("3500.00")
    finally:
        a.disconnect()
