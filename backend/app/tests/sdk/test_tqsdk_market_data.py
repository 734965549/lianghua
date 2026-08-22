"""TqSdk 独立行情适配器单测（Fake TqApi，不连真实行情）。"""

from __future__ import annotations

import math
import threading
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.broker.tqsdk_mapping import (
    normalize_tq_instrument_id,
    to_tq_quote_symbol,
    to_tq_symbol,
)
from app.schemas.enums import Market
from app.sdk.factory import get_adapter, resolve_quote_provider
from app.sdk.market_data.factory import get_market_data_adapter
from app.sdk.market_data.tqsdk_adapter import (
    TqSdkMarketDataAdapter,
    _INTERVAL_SECONDS,
    quote_from_tq,
)
from app.sdk.models import QuoteSnapshot


class FakeQuote:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeApi:
    def __init__(self, *, fail_after: int = 0):
        self.quotes: dict[str, FakeQuote] = {}
        self.closed = False
        self.wait_calls = 0
        self.fail_after = fail_after
        self._changing: set[str] = set()
        self.thread_id: int | None = None

    def get_quote(self, symbol: str):
        self.thread_id = threading.get_ident()
        if symbol not in self.quotes:
            self.quotes[symbol] = FakeQuote(
                last_price=3500.0,
                bid_price1=3499.0,
                ask_price1=3501.0,
                bid_volume1=10,
                ask_volume1=12,
                volume=1000,
                datetime="2026-08-22 10:00:00.000000",
                pre_close=3400.0,
                pre_settlement=3410.0,
                open=3450.0,
                highest=3520.0,
                lowest=3440.0,
                open_interest=20000,
                upper_limit=3700.0,
                lower_limit=3100.0,
                exchange_id="SHFE",
                instrument_id="rb2610",
                underlying_symbol="SHFE.rb2610",
                ins_class="FUTURE",
            )
        return self.quotes[symbol]

    @staticmethod
    def _serial(rows: list[dict]):
        class _Serial(list):
            def __init__(self, items):
                super().__init__(items)

            @property
            def iloc(self):
                parent = self

                class _ILoc:
                    def __getitem__(self, index):
                        return parent[index]

                return _ILoc()

        return _Serial(rows)

    def get_kline_serial(self, symbol: str, duration_seconds: int, data_length: int = 200):
        self.thread_id = threading.get_ident()
        rows = []
        for index in range(min(3, data_length)):
            rows.append(
                {
                    "datetime": f"2026-08-22 10:{index:02d}:00.000000",
                    "open": 3500 + index,
                    "high": 3510 + index,
                    "low": 3490 + index,
                    "close": 3505 + index,
                    "volume": 100 + index,
                }
            )
        _ = (symbol, duration_seconds)
        return self._serial(rows)

    def get_tick_serial(self, symbol: str, data_length: int = 200):
        self.thread_id = threading.get_ident()
        _ = symbol
        rows = [
            {
                "datetime": "2026-08-22 10:00:01.000000",
                "last_price": 3500.0,
                "bid_price1": 3499.0,
                "ask_price1": 3501.0,
                "volume": 100,
            },
            {
                "datetime": "2026-08-22 10:00:02.000000",
                "last_price": 3501.0,  # >= ask → buy
                "bid_price1": 3499.0,
                "ask_price1": 3501.0,
                "volume": 103,
            },
            {
                "datetime": "2026-08-22 10:00:03.000000",
                "last_price": 3498.0,  # <= bid → sell
                "bid_price1": 3499.0,
                "ask_price1": 3501.0,
                "volume": 108,
            },
        ]
        return self._serial(rows[: min(len(rows), data_length)])

    def wait_update(self, deadline=None):
        self.wait_calls += 1
        self.thread_id = threading.get_ident()
        _ = deadline
        if self.fail_after and self.wait_calls >= self.fail_after:
            raise RuntimeError("simulated disconnect")
        return True

    def is_changing(self, quote_obj):
        for symbol, ref in self.quotes.items():
            if ref is quote_obj:
                return symbol in self._changing
        return False

    def close(self):
        self.closed = True


@pytest.fixture
def fake_api():
    return FakeApi()


@pytest.fixture
def adapter(fake_api):
    md = TqSdkMarketDataAdapter(
        market=Market.FUTURES,
        config={
            "tqsdk_auth_user": "demo",
            "tqsdk_auth_password": "secret",
            "tqsdk_command_timeout_seconds": 5,
        },
        api_factory=lambda _cfg: fake_api,
    )
    md.connect()
    yield md
    md.disconnect()


def test_actual_contract_and_main_continuous_mapping():
    assert to_tq_symbol("rb2610", "SHFE") == "SHFE.rb2610"
    assert to_tq_quote_symbol("RB0") == "KQ.m@SHFE.rb"
    assert to_tq_quote_symbol("AU0") == "KQ.m@SHFE.au"
    assert to_tq_quote_symbol("IF0") == "KQ.m@CFFEX.IF"
    assert to_tq_quote_symbol("rb2610", "SHFE") == "SHFE.rb2610"


def test_cffex_czce_case_normalization():
    assert normalize_tq_instrument_id("if2509", "CFFEX") == "IF2509"
    assert normalize_tq_instrument_id("SR509", "CZCE") == "SR509"
    assert normalize_tq_instrument_id("RB2610", "SHFE") == "rb2610"
    assert to_tq_quote_symbol("IF2509", "CFFEX") == "CFFEX.IF2509"
    assert to_tq_quote_symbol("sr509", "CZCE") == "CZCE.SR509"


def test_quote_from_tq_filters_nan_and_empty():
    bad = FakeQuote(
        last_price=float("nan"),
        datetime="2026-08-22 10:00:00.000000",
        volume=1,
        pre_close=100,
    )
    assert quote_from_tq(
        project_symbol="RB0",
        market=Market.FUTURES,
        tq_symbol="KQ.m@SHFE.rb",
        quote_obj=bad,
    ) is None

    empty_time = FakeQuote(last_price=3500, datetime="", volume=1, pre_close=3400)
    assert quote_from_tq(
        project_symbol="RB0",
        market=Market.FUTURES,
        tq_symbol="KQ.m@SHFE.rb",
        quote_obj=empty_time,
    ) is None

    zero = FakeQuote(last_price=0, datetime="2026-08-22 10:00:00", volume=1, pre_close=1)
    assert quote_from_tq(
        project_symbol="RB0",
        market=Market.FUTURES,
        tq_symbol="KQ.m@SHFE.rb",
        quote_obj=zero,
    ) is None


def test_quote_snapshot_field_mapping():
    quote = FakeQuote(
        last_price=3500.0,
        bid_price1=3499.0,
        ask_price1=3501.0,
        bid_volume1=10,
        ask_volume1=12,
        volume=1000,
        datetime="2026-08-22 10:00:00.000000",
        pre_close=3400.0,
        pre_settlement=3410.0,
        open=3450.0,
        highest=3520.0,
        lowest=3440.0,
        open_interest=20000,
        upper_limit=3700.0,
        lower_limit=3100.0,
        exchange_id="SHFE",
        instrument_id="rb",
        underlying_symbol="SHFE.rb2610",
        ins_class="CONT",
    )
    snap = quote_from_tq(
        project_symbol="RB0",
        market=Market.FUTURES,
        tq_symbol="KQ.m@SHFE.rb",
        quote_obj=quote,
    )
    assert snap is not None
    assert snap.symbol == "RB0"
    assert snap.last_price == Decimal("3500.0")
    assert snap.bid_price == Decimal("3499.0")
    assert snap.ask_price == Decimal("3501.0")
    assert snap.bid_volume == Decimal("10")
    assert snap.ask_volume == Decimal("12")
    assert snap.change_rate == (Decimal("3500.0") - Decimal("3400.0")) / Decimal("3400.0")
    assert snap.raw_payload["provider"] == "tqsdk"
    assert snap.raw_payload["underlying_symbol"] == "SHFE.rb2610"
    assert not math.isnan(float(snap.last_price))


def test_subscribe_unsubscribe_and_dedupe(adapter, fake_api):
    emitted: list[QuoteSnapshot] = []
    adapter.on_quote_update(emitted.append)

    adapter.subscribe_quotes(["RB0"])
    assert "RB0" in adapter._runtime._project_to_tq
    assert adapter._runtime._project_to_tq["RB0"] == "KQ.m@SHFE.rb"
    assert len(emitted) == 1

    # 相同快照不重复推送
    adapter._runtime._poll_quotes()
    assert len(emitted) == 1

    fake_api._changing.add("KQ.m@SHFE.rb")
    fake_api.quotes["KQ.m@SHFE.rb"].last_price = 3510.0
    adapter._runtime._poll_quotes()
    assert len(emitted) == 2
    assert emitted[-1].last_price == Decimal("3510.0")

    adapter.unsubscribe_quotes(["RB0"])
    assert "RB0" not in adapter._runtime._project_to_tq


def test_get_quote_returns_project_symbol(adapter):
    snap = adapter.get_quote("RB0")
    assert snap.symbol == "RB0"
    assert snap.raw_payload["tq_symbol"] == "KQ.m@SHFE.rb"


def test_kline_interval_mapping_and_get_kline(adapter):
    assert _INTERVAL_SECONDS["1m"] == 60
    assert _INTERVAL_SECONDS["5m"] == 300
    assert _INTERVAL_SECONDS["1d"] == 86400
    bars = adapter.get_kline(
        "RB0",
        "1m",
        datetime(2026, 8, 22, tzinfo=timezone.utc),
        datetime(2026, 8, 23, tzinfo=timezone.utc),
    )
    assert len(bars) >= 1
    assert bars[0].symbol == "RB0"
    assert bars[0].interval == "1m"


def test_tqapi_only_on_worker_thread(adapter, fake_api):
    main_tid = threading.get_ident()
    adapter.subscribe_quotes(["RB0"])
    assert fake_api.thread_id is not None
    assert fake_api.thread_id != main_tid
    # 对外 call 必须从非工作线程发起；健康检查应成功返回
    health = adapter._runtime.call("health")
    assert health["connected"] is True


def test_factory_stock_tqsdk_rejected():
    with pytest.raises(ValueError, match="仅支持期货"):
        get_market_data_adapter(Market.STOCK, "tqsdk", {"tqsdk_auth_user": "a", "tqsdk_auth_password": "b"})


def test_resolve_quote_provider_split_and_fallback():
    assert (
        resolve_quote_provider(
            Market.STOCK,
            {"quote_provider": "ifind", "stock_quote_provider": "akshare"},
        )
        == "akshare"
    )
    assert (
        resolve_quote_provider(
            Market.FUTURES,
            {"quote_provider": "akshare", "futures_quote_provider": "tqsdk"},
        )
        == "tqsdk"
    )
    assert resolve_quote_provider(Market.FUTURES, {"quote_provider": "mock"}) == "mock"


def test_tqsdk_market_data_works_without_trading_broker_account(fake_api):
    """交易关闭时，仅快期账号仍可运行免费行情。"""
    md = TqSdkMarketDataAdapter(
        market=Market.FUTURES,
        config={
            "tqsdk_auth_user": "demo",
            "tqsdk_auth_password": "secret",
            # 故意不提供 broker/account/password
        },
        api_factory=lambda _cfg: fake_api,
    )
    md.connect()
    try:
        snap = md.get_quote("RB0")
        assert snap.last_price > 0
    finally:
        md.disconnect()


def test_get_adapter_tqsdk_does_not_enable_futures_trading_adapter(fake_api, monkeypatch):
    monkeypatch.setattr(
        "app.sdk.market_data.tqsdk_adapter.create_tq_quote_api",
        lambda _cfg: fake_api,
    )
    adapter = get_adapter(
        Market.FUTURES,
        {
            "mode": "real",
            "futures_quote_provider": "tqsdk",
            "tqsdk_auth_user": "demo",
            "tqsdk_auth_password": "secret",
        },
    )
    assert adapter.name == "tqsdk"
    trading = getattr(adapter, "_trading", None) or getattr(adapter, "_trading_adapter", None)
    assert trading is not None
    assert trading.__class__.__name__ == "MockTradingAdapter"


def test_broker_supports_market_data_flag():
    from app.broker.base import Broker
    from app.broker.ctp_broker import CTPBroker
    from app.broker.tqsdk_broker import TqSdkBroker

    assert Broker.supports_market_data is False
    assert CTPBroker.supports_market_data is True
    assert TqSdkBroker.supports_market_data is False


def test_get_tick_trades_maps_direction_and_volume_delta(adapter):
    trades = adapter.get_tick_trades("RB0", limit=10)
    assert len(trades) >= 2
    assert set(trades[0]) >= {"time", "price", "volume", "direction"}
    # 最新在前：最后一笔卖出 3498，增量成交量 5
    assert trades[0]["price"] == "3498.0"
    assert trades[0]["direction"] == "sell"
    assert trades[0]["volume"] == "5"
    assert trades[1]["direction"] == "buy"
    assert trades[1]["volume"] == "3"


def test_auto_reconnect_restores_subscription():
    import time

    created: list[FakeApi] = []
    events: list[tuple[bool, str]] = []

    def factory(_cfg):
        api = FakeApi(fail_after=0)
        created.append(api)
        return api

    md = TqSdkMarketDataAdapter(
        market=Market.FUTURES,
        config={
            "tqsdk_auth_user": "demo",
            "tqsdk_auth_password": "secret",
            "tqsdk_command_timeout_seconds": 15,
            "tqsdk_reconnect_max_seconds": 2,
        },
        api_factory=factory,
    )
    md.on_connection_change(lambda ok, reason: events.append((ok, reason)))
    md.connect()
    try:
        md.subscribe_quotes(["RB0"])
        assert created, "首个 TqApi 未创建"
        # 连接稳定后再注入断线，避免与 start() 竞态
        created[0].fail_after = 1
        deadline = time.time() + 12
        while time.time() < deadline:
            health = md._runtime.health()
            if health["reconnect_count"] >= 1 and health["connected"]:
                break
            time.sleep(0.1)
        health = md._runtime.health()
        assert health["reconnect_count"] >= 1
        assert health["connected"] is True
        assert "RB0" in md._runtime._quote_refs
        assert any(ok is False for ok, _ in events)
        assert any(ok and "reconnect" in reason for ok, reason in events)
        snap = md.get_quote("RB0")
        assert snap.symbol == "RB0"
        assert snap.last_price > 0
        assert len(created) >= 2
        assert created[0].closed is True
    finally:
        md.disconnect()
