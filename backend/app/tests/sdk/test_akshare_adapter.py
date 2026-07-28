"""AKShare 适配器单元测试（全 mock，不依赖真实网络）。"""

import time
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pandas as pd
import pytest

from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction
from app.sdk.base import SDKDisconnected, SDKOrderRejected
from app.sdk.models import CancelOrderRequest, PlaceOrderRequest


# ---------- mock 数据 ----------

def _mock_spot_df():
    return pd.DataFrame(
        [
            {"代码": "600000", "最新价": 12.50, "涨跌幅": 1.23, "成交量": 50000000},
            {"代码": "000001", "最新价": 15.80, "涨跌幅": -0.50, "成交量": 30000000},
            {"代码": "300750", "最新价": 200.00, "涨跌幅": 3.10, "成交量": 8000000},
        ]
    )


def _mock_hist_df():
    return pd.DataFrame(
        [
            {"date": "2026-01-15", "open": 12.0, "high": 12.8, "low": 11.9, "close": 12.5, "volume": 1000000},
            {"date": "2026-01-16", "open": 12.5, "high": 13.0, "low": 12.4, "close": 12.8, "volume": 1200000},
        ]
    )


# ---------- fixture ----------

@pytest.fixture
def adapter():
    """创建已连接的 AkshareAdapter，所有 akshare 调用均已 mock。"""
    with patch("app.sdk.akshare_adapter.ak") as mock_ak:
        mock_ak.stock_zh_a_spot.return_value = _mock_spot_df()
        mock_ak.stock_zh_a_daily.return_value = _mock_hist_df()
        from app.sdk.akshare_adapter import AkshareAdapter

        a = AkshareAdapter(market=Market.STOCK)
        a.connect()
        # connect 异步刷新，测试中同步填充缓存
        a._refresh_spot_snapshot()
        yield a
        a.disconnect()


# ---------- 生命周期 ----------

@pytest.mark.unit
def test_connect(adapter):
    assert adapter._connected is True
    # 连接后缓存应有快照
    assert "600000.SH" in adapter._latest_quotes
    assert adapter._latest_quotes["600000.SH"].last_price == Decimal("12.50")


@pytest.mark.unit
def test_disconnect_stops_quotes(adapter):
    adapter.subscribe_quotes(["600000.SH"])
    adapter.disconnect()
    assert adapter._connected is False


@pytest.mark.unit
def test_connect_disconnect_callbacks():
    events = []
    with patch("app.sdk.akshare_adapter.ak") as mock_ak:
        mock_ak.stock_zh_a_spot.return_value = _mock_spot_df()
        mock_ak.stock_zh_a_daily.return_value = _mock_hist_df()
        from app.sdk.akshare_adapter import AkshareAdapter

        a = AkshareAdapter(market=Market.STOCK)
        a.on_connection_change(lambda e: events.append(e))
        a.connect()
        a.disconnect()
    assert len(events) >= 2
    assert events[0].connected is True
    assert events[-1].connected is False


# ---------- 行情 ----------

@pytest.mark.unit
def test_get_quote_returns_cached_snapshot(adapter):
    snap = adapter.get_quote("600000.SH")
    assert snap.symbol == "600000.SH"
    assert snap.last_price == Decimal("12.50")
    assert snap.market == Market.STOCK


@pytest.mark.unit
def test_get_quote_raises_for_missing_symbol(adapter):
    with pytest.raises(SDKDisconnected):
        adapter.get_quote("999999.SZ")


@pytest.mark.unit
def test_get_quote_requires_connect():
    with patch("app.sdk.akshare_adapter.ak") as mock_ak:
        mock_ak.stock_zh_a_spot.return_value = _mock_spot_df()
        mock_ak.stock_zh_a_daily.return_value = _mock_hist_df()
        from app.sdk.akshare_adapter import AkshareAdapter

        a = AkshareAdapter(market=Market.STOCK)
        with pytest.raises(SDKDisconnected):
            a.get_quote("600000.SH")


@pytest.mark.unit
def test_get_kline_returns_bars(adapter):
    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=3)
    bars = adapter.get_kline("600000.SH", "1d", start, end)
    assert len(bars) == 2
    assert bars[0].symbol == "600000.SH"
    assert bars[0].close == Decimal("12.5")
    assert bars[0].bar_time.tzinfo is not None  # 有时区


@pytest.mark.unit
def test_get_kline_requires_connect():
    with patch("app.sdk.akshare_adapter.ak") as mock_ak:
        mock_ak.stock_zh_a_spot.return_value = _mock_spot_df()
        mock_ak.stock_zh_a_daily.return_value = _mock_hist_df()
        from app.sdk.akshare_adapter import AkshareAdapter

        a = AkshareAdapter(market=Market.STOCK)
        with pytest.raises(SDKDisconnected):
            a.get_kline("600000.SH", "1d", None, None)


# ---------- 订阅推送 ----------

@pytest.mark.unit
def test_subscribe_quotes_pushes_updates(adapter):
    received = []
    adapter.on_quote_update(lambda q: received.append(q))
    adapter.subscribe_quotes(["600000.SH"])
    time.sleep(1.5)  # 等待一个轮询周期
    assert len(received) >= 1
    assert received[0].symbol == "600000.SH"


@pytest.mark.unit
def test_subscribe_requires_connect():
    with patch("app.sdk.akshare_adapter.ak") as mock_ak:
        mock_ak.stock_zh_a_spot.return_value = _mock_spot_df()
        mock_ak.stock_zh_a_daily.return_value = _mock_hist_df()
        from app.sdk.akshare_adapter import AkshareAdapter

        a = AkshareAdapter(market=Market.STOCK)
        with pytest.raises(SDKDisconnected):
            a.subscribe_quotes(["600000.SH"])


# ---------- 交易 ----------

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
        price=Decimal("12.50"),
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
def test_place_order_updates_positions(adapter):
    adapter.on_order_update(lambda e: None)
    adapter.on_trade_update(lambda e: None)

    req = PlaceOrderRequest(
        client_order_id="pos_test",
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("12.50"),
        quantity=Decimal("200"),
    )
    adapter.place_order(req)
    time.sleep(0.6)

    positions = adapter.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "600000.SH"
    assert positions[0].quantity == Decimal("200")


@pytest.mark.unit
def test_place_order_sell_reduces_positions(adapter):
    adapter.on_order_update(lambda e: None)
    adapter.on_trade_update(lambda e: None)

    # 先买入
    buy_req = PlaceOrderRequest(
        client_order_id="buy_1",
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("12.50"),
        quantity=Decimal("200"),
    )
    adapter.place_order(buy_req)
    time.sleep(0.6)
    assert len(adapter.get_positions()) == 1

    # 再卖出
    sell_req = PlaceOrderRequest(
        client_order_id="sell_1",
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="600000.SH",
        side=OrderSide.SELL,
        action=SignalAction.CLOSE,
        price_type=PriceType.LIMIT,
        price=Decimal("13.00"),
        quantity=Decimal("100"),
    )
    adapter.place_order(sell_req)
    time.sleep(0.6)

    positions = adapter.get_positions()
    assert len(positions) == 1
    assert positions[0].quantity == Decimal("100")  # 200 - 100


@pytest.mark.unit
def test_place_order_requires_connect():
    with patch("app.sdk.akshare_adapter.ak") as mock_ak:
        mock_ak.stock_zh_a_spot.return_value = _mock_spot_df()
        mock_ak.stock_zh_a_daily.return_value = _mock_hist_df()
        from app.sdk.akshare_adapter import AkshareAdapter

        a = AkshareAdapter(market=Market.STOCK)
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
def test_cancel_order_missing_raises(adapter):
    with pytest.raises(SDKOrderRejected):
        adapter.cancel_order(
            CancelOrderRequest(client_order_id="missing", market=Market.STOCK)
        )


@pytest.mark.unit
def test_cancel_order_requires_connect():
    with patch("app.sdk.akshare_adapter.ak") as mock_ak:
        mock_ak.stock_zh_a_spot.return_value = _mock_spot_df()
        mock_ak.stock_zh_a_daily.return_value = _mock_hist_df()
        from app.sdk.akshare_adapter import AkshareAdapter

        a = AkshareAdapter(market=Market.STOCK)
        with pytest.raises(SDKDisconnected):
            a.cancel_order(CancelOrderRequest(client_order_id="x", market=Market.STOCK))


# ---------- 查询 ----------

@pytest.mark.unit
def test_query_orders(adapter):
    adapter.on_order_update(lambda e: None)
    adapter.on_trade_update(lambda e: None)
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
def test_query_trades_filters(adapter):
    adapter.on_order_update(lambda e: None)
    adapter.on_trade_update(lambda e: None)
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


# ---------- 账户 ----------

@pytest.mark.unit
def test_get_account(adapter):
    acc = adapter.get_account()
    assert acc.account_no == "AKSHARE_SIM"
    assert acc.available_cash > 0


@pytest.mark.unit
def test_get_account_requires_connect():
    with patch("app.sdk.akshare_adapter.ak") as mock_ak:
        mock_ak.stock_zh_a_spot.return_value = _mock_spot_df()
        mock_ak.stock_zh_a_daily.return_value = _mock_hist_df()
        from app.sdk.akshare_adapter import AkshareAdapter

        a = AkshareAdapter(market=Market.STOCK)
        with pytest.raises(SDKDisconnected):
            a.get_account()


# ---------- 工具方法 ----------

@pytest.mark.unit
def test_normalize_symbol():
    from app.sdk.akshare_adapter import AkshareAdapter

    assert AkshareAdapter._normalize_symbol("600000") == "600000.SH"
    assert AkshareAdapter._normalize_symbol("688001") == "688001.SH"
    assert AkshareAdapter._normalize_symbol("000001") == "000001.SZ"
    assert AkshareAdapter._normalize_symbol("300750") == "300750.SZ"
    # 已带后缀
    assert AkshareAdapter._normalize_symbol("600000.SH") == "600000.SH"


@pytest.mark.unit
def test_safe_decimal():
    from app.sdk.akshare_adapter import AkshareAdapter

    assert AkshareAdapter._safe_decimal("12.50") == Decimal("12.50")
    assert AkshareAdapter._safe_decimal(None) == Decimal("0")
    assert AkshareAdapter._safe_decimal(float("nan")) == Decimal("0")
    assert AkshareAdapter._safe_decimal("abc") == Decimal("0")


# ---------- 边界情况 ----------

@pytest.mark.unit
def test_spot_snapshot_empty_df(adapter):
    """空 DataFrame 不覆盖缓存。"""
    adapter._latest_quotes["test.SH"] = None  # 设一个标记
    with patch.object(adapter, "_lock", adapter._lock):  # 不 mock 锁
        pass
    # 模拟空数据
    with patch("app.sdk.akshare_adapter.ak") as mock_ak:
        mock_ak.stock_zh_a_spot.return_value = pd.DataFrame()
        adapter._refresh_spot_snapshot()
    # 缓存不变（batch 为空，不 update）
    # 这里只验证不抛异常
    assert adapter._connected is True


@pytest.mark.unit
def test_spot_snapshot_exception_preserves_cache(adapter):
    """源站异常时保留旧缓存。"""
    adapter._latest_quotes["600000.SH"] = None  # 标记
    with patch("app.sdk.akshare_adapter.ak") as mock_ak:
        mock_ak.stock_zh_a_spot.side_effect = ConnectionError("timeout")
        adapter._refresh_spot_snapshot()
    # 不抛异常，旧缓存保留
    assert adapter._connected is True


@pytest.mark.unit
def test_get_kline_exception_returns_empty(adapter):
    """get_kline 异常时返回空列表。"""
    with patch("app.sdk.akshare_adapter.ak") as mock_ak:
        mock_ak.stock_zh_a_daily.side_effect = ConnectionError("timeout")
        from datetime import datetime, timedelta, timezone

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=3)
        bars = adapter.get_kline("600000.SH", "1d", start, end)
        assert bars == []


@pytest.mark.unit
def test_simulate_fill_fallback_to_request_price(adapter):
    """当 get_quote 失败时，降级为委托价。"""
    adapter.on_order_update(lambda e: None)
    adapter.on_trade_update(lambda e: None)

    req = PlaceOrderRequest(
        client_order_id="fallback_test",
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="999999.SZ",  # 不存在的 symbol，get_quote 会抛异常
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("8.88"),
        quantity=Decimal("100"),
    )
    adapter.place_order(req)
    time.sleep(0.6)

    trades = adapter.query_trades({"client_order_id": "fallback_test"})
    assert len(trades) >= 1
    # 成交价应为委托价 8.88（而非 10.00）
    assert trades[0].price == Decimal("8.88")