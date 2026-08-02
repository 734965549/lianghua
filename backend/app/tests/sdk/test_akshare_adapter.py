"""AKShare 适配器单元测试（全 mock，不依赖真实网络）。"""

import time
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
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


def _mock_spot_rows():
    return [
        {"f12": "600000", "f14": "浦发银行", "f2": 12.50, "f3": 1.23, "f5": 50000000},
        {"f12": "000001", "f14": "平安银行", "f2": 15.80, "f3": -0.50, "f5": 30000000},
        {"f12": "300750", "f14": "宁德时代", "f2": 200.00, "f3": 3.10, "f5": 8000000},
    ]


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

        a = AkshareAdapter(
            market=Market.STOCK,
            config={
                "akshare_background_sync": False,
                "akshare_poll_seconds": 0.05,
                "akshare_retry_backoff": 0,
            },
        )
        a.connect()
        a._update_spot_batch(_mock_spot_rows())
        a._spot_sync_done.set()
        yield a
        a.disconnect()


# ---------- 生命周期 ----------

@pytest.mark.unit
def test_connect(adapter):
    assert adapter._connected is True
    # 连接后缓存应有快照
    assert "600000.SH" in adapter._latest_quotes
    assert adapter._latest_quotes["600000.SH"].last_price == Decimal("12.50")
    assert adapter._latest_quotes["600000.SH"].change_rate == Decimal("0.0123")


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

        a = AkshareAdapter(
            market=Market.STOCK,
            config={"akshare_background_sync": False},
        )
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
def test_list_stock_instruments(adapter):
    adapter._latest_quotes.clear()
    adapter._update_spot_batch(
        [
            {"code": "600000", "name": "浦发银行", "trade": 12.5},
            {"code": "430047", "name": "诺思兰德", "trade": 18.8},
        ]
    )

    instruments = adapter.list_instruments()

    assert instruments[0]["symbol"] == "600000.SH"
    assert instruments[1]["symbol"] == "430047.BJ"


@pytest.mark.unit
def test_list_futures_instruments_covers_all_domestic_exchanges():
    from app.sdk.akshare_adapter import AkshareAdapter

    futures = AkshareAdapter(
        market=Market.FUTURES,
        config={"akshare_background_sync": False},
    )

    instruments = futures.list_instruments()

    symbols = {item["symbol"] for item in instruments}
    exchanges = {item["exchange"] for item in instruments}
    assert len(instruments) >= 80
    assert {"RB0", "CU0", "SC0", "M0", "TA0", "LC0", "IF0"} <= symbols
    assert {"SHFE", "INE", "DCE", "CZCE", "GFEX", "CFFEX"} <= exchanges
    futures.disconnect()


@pytest.mark.unit
def test_futures_quote_fetches_requested_contract_and_uses_bare_symbol():
    from app.sdk.akshare_adapter import AkshareAdapter

    futures = AkshareAdapter(
        market=Market.FUTURES,
        config={
            "akshare_background_sync": False,
            "akshare_max_retries": 0,
        },
    )
    futures.connect()
    response = (
        'var hq_str_nf_RB0="螺纹钢连续,15:00:00,3500,3600,3450,3520,'
        '3550,3552,3551,3540,3530,20,30,10000,20000";'
    )
    with patch.object(futures, "_request_text", return_value=response) as request:
        quote = futures.get_quote("rb0.SHFE")

    assert quote.symbol == "RB0"
    assert quote.last_price == Decimal("3551")
    assert quote.change_rate == pytest.approx(Decimal("0.005949008498583569405099150142"))
    assert quote.bid_price == Decimal("3550")
    assert quote.ask_price == Decimal("3552")
    assert quote.volume == Decimal("20000")
    assert request.call_args.kwargs["params"]["list"] == "nf_RB0"
    futures.disconnect()


@pytest.mark.unit
def test_futures_quote_parser_does_not_treat_ta_as_cffex_treasury():
    from app.sdk.akshare_adapter import AkshareAdapter

    futures = AkshareAdapter(market=Market.FUTURES)
    response = (
        'var hq_str_nf_TA0="PTA连续,15:00:00,4800,4900,4750,4810,'
        '4848,4850,4849,4830,4820,100,120,500000,900000";'
    )

    quotes = futures._parse_futures_response(response, ["TA0"])

    assert quotes["TA0"].last_price == Decimal("4849")
    assert quotes["TA0"].volume == Decimal("900000")
    futures.disconnect()


@pytest.mark.unit
def test_futures_refresh_uses_failure_cooldown():
    from app.sdk.akshare_adapter import AkshareAdapter

    futures = AkshareAdapter(
        market=Market.FUTURES,
        config={"akshare_max_retries": 0},
    )
    futures.connect()
    with patch.object(
        futures,
        "_request_text",
        side_effect=SDKDisconnected("vpn blocked"),
    ) as request:
        futures._refresh_futures_snapshot(["RB0"])
        futures._refresh_futures_snapshot(["RB0"])

    request.assert_called_once()
    futures.disconnect()


@pytest.mark.unit
def test_get_quote_raises_for_missing_symbol(adapter):
    with patch.object(
        adapter,
        "_fetch_stock_quote",
        side_effect=SDKDisconnected("missing"),
    ):
        with pytest.raises(SDKDisconnected):
            adapter.get_quote("999999.SZ")


@pytest.mark.unit
def test_get_quote_cache_miss_uses_lightweight_single_stock(adapter):
    expected = adapter._latest_quotes["600000.SH"].model_copy(
        update={"symbol": "601398.SH"}
    )
    with (
        patch.object(adapter, "_fetch_stock_quote", return_value=expected) as fetch,
        patch.object(adapter, "_refresh_spot_snapshot") as full_refresh,
    ):
        result = adapter.get_quote("601398.SH")

    assert result == expected
    fetch.assert_called_once_with("601398.SH")
    full_refresh.assert_not_called()


@pytest.mark.unit
def test_get_quote_does_not_block_during_background_full_sync(adapter):
    adapter._background_sync_enabled = True
    adapter._spot_sync_done.clear()
    adapter._sync_thread = MagicMock()
    adapter._sync_thread.is_alive.return_value = True

    with patch.object(adapter, "_fetch_stock_quote") as fetch:
        with pytest.raises(SDKDisconnected, match="全市场行情同步中"):
            adapter.get_quote("601398.SH")

    fetch.assert_not_called()


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
def test_get_minute_kline_prefers_sina_and_converts_exchange_time_to_utc(adapter):
    from datetime import datetime, timezone

    provider = MagicMock()
    provider.stock_zh_a_minute.return_value = pd.DataFrame(
        [
            {
                "day": "2026-07-31 14:59:00",
                "open": 11.61,
                "high": 11.63,
                "low": 11.60,
                "close": 11.63,
                "volume": 1000,
            }
        ]
    )
    with patch.object(adapter, "_ak", return_value=provider):
        bars = adapter.get_kline(
            "000001.SZ",
            "1m",
            datetime(2026, 7, 31, 6, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 31, 8, 0, tzinfo=timezone.utc),
        )

    assert len(bars) == 1
    assert bars[0].bar_time.isoformat() == "2026-07-31T06:59:00+00:00"
    assert bars[0].close == Decimal("11.63")
    provider.stock_zh_a_minute.assert_called_once_with(
        symbol="sz000001",
        period="1",
        adjust="qfq",
    )
    provider.stock_zh_a_hist_min_em.assert_not_called()


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
    assert AkshareAdapter._normalize_symbol("920000") == "920000.BJ"
    assert AkshareAdapter._normalize_symbol("bj920006") == "920006.BJ"
    assert AkshareAdapter._normalize_symbol("BJ920006.SZ") == "920006.BJ"
    assert AkshareAdapter._normalize_symbol("sh600000") == "600000.SH"
    # 已带后缀
    assert AkshareAdapter._normalize_symbol("600000.SH") == "600000.SH"
    assert AkshareAdapter._normalize_futures_symbol("rb0.SHFE") == "RB0"


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
    """空分页结果不覆盖缓存。"""
    adapter._latest_quotes["test.SH"] = None  # 设一个标记
    with patch.object(adapter, "_fetch_spot_page", return_value=([], 1)):
        adapter._refresh_spot_snapshot()
    assert "test.SH" in adapter._latest_quotes


@pytest.mark.unit
def test_spot_snapshot_exception_preserves_cache(adapter):
    """源站异常时保留旧缓存。"""
    adapter._latest_quotes["600000.SH"] = None  # 标记
    with patch.object(
        adapter,
        "_fetch_spot_page",
        side_effect=ConnectionError("timeout"),
    ):
        adapter._refresh_spot_snapshot()
    assert "600000.SH" in adapter._latest_quotes
    assert adapter._last_refresh_error == "timeout"


@pytest.mark.unit
def test_spot_snapshot_updates_cache_page_by_page(adapter):
    page_one = [_mock_spot_rows()[0]]
    page_two = [_mock_spot_rows()[1]]
    with patch.object(
        adapter,
        "_fetch_spot_page",
        side_effect=[(page_one, 2), (page_two, 2)],
    ) as fetch:
        adapter._refresh_spot_snapshot()

    assert fetch.call_count == 2
    assert adapter._latest_quotes["600000.SH"].last_price == Decimal("12.50")
    assert adapter._latest_quotes["000001.SZ"].last_price == Decimal("15.80")


@pytest.mark.unit
def test_spot_batch_ignores_non_stock_codes(adapter):
    adapter._update_spot_batch(
        [
            {"code": "BK1627", "name": "行业板块", "trade": 100},
            {"code": "sh000001", "name": "上证指数", "trade": 3000},
            {"code": "920000", "name": "北交所股票", "trade": 14.9},
        ]
    )

    assert "BK1627.SZ" not in adapter._latest_quotes
    assert "sh000001.SZ" not in adapter._latest_quotes
    assert adapter._latest_quotes["920000.BJ"].last_price == Decimal("14.9")


@pytest.mark.unit
def test_request_json_retries_after_timeout(adapter):
    request = httpx.Request("GET", "https://example.test/quotes")
    response = httpx.Response(
        200,
        request=request,
        json={"data": {"ok": True}},
    )
    timeout = httpx.ReadTimeout("timeout", request=request)
    adapter._max_retries = 1
    adapter._retry_backoff = 0

    with patch.object(
        adapter._http_client,
        "get",
        side_effect=[timeout, response],
    ) as get:
        payload = adapter._request_json(
            "https://example.test/quotes",
            params={"symbol": "600000"},
        )

    assert payload["data"]["ok"] is True
    assert get.call_count == 2


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
    with patch.object(
        adapter,
        "_fetch_stock_quote",
        side_effect=SDKDisconnected("missing"),
    ):
        adapter.place_order(req)
        time.sleep(0.6)

    trades = adapter.query_trades({"client_order_id": "fallback_test"})
    assert len(trades) >= 1
    # 成交价应为委托价 8.88（而非 10.00）
    assert trades[0].price == Decimal("8.88")
