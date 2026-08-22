"""TqSdkBroker / Runtime 单元测试（Fake TqApi，不连真实柜台）。"""

from __future__ import annotations

import threading
import time
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.broker import manager as broker_manager
from app.broker.errors import (
    BrokerConfigurationError,
    BrokerSubmitOutcomeUnknown,
    BrokerSubmitRejected,
)
from app.broker.tqsdk_broker import TqSdkBroker
from app.broker.tqsdk_mapping import (
    client_order_id_to_tq_order_id,
    map_offset,
    map_order_status,
    to_tq_symbol,
)
from app.broker.tqsdk_runtime import TqSdkRuntime
from app.core.config import settings
from app.schemas.enums import (
    HedgeFlag,
    Market,
    OffsetFlag,
    OrderSide,
    OrderStatus,
    PriceType,
    SignalAction,
)
from app.sdk.models import CancelOrderRequest, PlaceOrderRequest


class FakeOrder(SimpleNamespace):
    pass


class FakeTrade(SimpleNamespace):
    pass


class FakeTqApi:
    def __init__(self):
        self.account = SimpleNamespace(
            balance=1_000_000,
            available=800_000,
            margin=50_000,
            frozen_margin=1_000,
            commission=20,
            close_profit=100,
            position_profit=-50,
            risk_ratio=0.05,
        )
        self.positions = {
            "SHFE.rb2610": SimpleNamespace(
                exchange_id="SHFE",
                instrument_id="rb2610",
                pos_long=2,
                pos_long_today=1,
                pos_long_his=1,
                pos_short=0,
                pos_short_today=0,
                pos_short_his=0,
                open_price_long=3500,
                open_price_short=0,
                margin_long=12000,
                margin_short=0,
                position_profit_long=200,
                position_profit_short=0,
            )
        }
        self.orders: dict[str, FakeOrder] = {}
        self.trades: dict[str, FakeTrade] = {}
        self._pending_orders: list[FakeOrder] = []
        self._closed = False
        self._lock = threading.Lock()
        self.fail_insert = False
        self.insert_never_ack = False

    def get_account(self):
        return self.account

    def get_position(self, symbol=None):
        if symbol:
            return self.positions.get(symbol)
        return dict(self.positions)

    def get_order(self, order_id=None):
        if order_id:
            return self.orders.get(order_id)
        return dict(self.orders)

    def get_trade(self, trade_id=None):
        if trade_id:
            return self.trades.get(trade_id)
        return dict(self.trades)

    def insert_order(self, symbol, direction, offset, volume, limit_price=None, order_id=None):
        if self.fail_insert:
            raise RuntimeError("network blip")
        oid = order_id or f"auto_{len(self.orders)+1}"
        order = FakeOrder(
            order_id=oid,
            exchange_order_id="",
            exchange_id=symbol.split(".", 1)[0],
            instrument_id=symbol.split(".", 1)[1],
            direction=direction,
            offset=offset,
            volume_orign=int(volume),
            volume_left=int(volume),
            limit_price=limit_price,
            status="" if self.insert_never_ack else "ALIVE",
            is_error=False,
            is_dead=False,
            last_msg="",
        )
        with self._lock:
            self.orders[oid] = order
            if self.insert_never_ack:
                self._pending_orders.append(order)
        return order

    def cancel_order(self, order_or_id):
        order_id = getattr(order_or_id, "order_id", None) or str(order_or_id)
        order = self.orders[order_id]
        order.status = "FINISHED"
        order.is_dead = True
        # 未成交撤单：保留 volume_left
        return order

    def wait_update(self, deadline=None):
        # 推进“延迟确认”的报单
        with self._lock:
            for order in self._pending_orders:
                if not order.status:
                    order.status = "ALIVE"
            self._pending_orders.clear()
        if deadline is not None:
            remain = max(0.0, float(deadline) - time.time())
            time.sleep(min(remain, 0.01))
        else:
            time.sleep(0.01)
        return True

    def close(self):
        self._closed = True


@pytest.fixture
def fake_api():
    return FakeTqApi()


@pytest.fixture
def broker(fake_api, monkeypatch):
    # 避免真实 DB：固定账户 UUID
    monkeypatch.setattr(
        TqSdkBroker,
        "_account_uuid",
        lambda self: uuid4(),
    )

    def factory(config, **callbacks):
        return TqSdkRuntime(config, api_factory=lambda: fake_api, **callbacks)

    b = TqSdkBroker(
        {
            "broker_id": "faka",
            "account_id": "12345678",
            "password": "secret",
            "auth_user": "tq_user",
            "auth_password": "tq_pass",
            "live_enabled": False,
            "live_arm_token": "arm-token",
            "command_timeout_seconds": 2.0,
            "command_queue_size": 100,
        },
        runtime_factory=factory,
    )
    yield b
    try:
        b.disconnect()
    except Exception:
        pass


def test_mapping_symbol_and_offset():
    assert to_tq_symbol("rb2610", "SHFE") == "SHFE.rb2610"
    assert to_tq_symbol("SHFE.rb2610") == "SHFE.rb2610"
    assert to_tq_symbol("RB2610.SHF") == "SHFE.rb2610"
    assert map_offset(OffsetFlag.OPEN, "SHFE") == "OPEN"
    assert map_offset(OffsetFlag.CLOSE_TODAY, "SHFE") == "CLOSETODAY"
    assert map_offset(OffsetFlag.CLOSE_YESTERDAY, "SHFE") == "CLOSE"
    with pytest.raises(ValueError):
        map_offset(OffsetFlag.CLOSE_TODAY, "DCE")


def test_map_order_status_matrix():
    assert map_order_status(FakeOrder(status="ALIVE", volume_orign=2, volume_left=2, is_error=False)) == OrderStatus.SUBMITTED
    assert map_order_status(FakeOrder(status="ALIVE", volume_orign=2, volume_left=1, is_error=False)) == OrderStatus.PARTIALLY_FILLED
    assert map_order_status(FakeOrder(status="FINISHED", volume_orign=2, volume_left=0, is_error=False)) == OrderStatus.FILLED
    assert map_order_status(FakeOrder(status="FINISHED", volume_orign=2, volume_left=1, is_error=False)) == OrderStatus.CANCELLED
    assert map_order_status(FakeOrder(status="FINISHED", volume_orign=2, volume_left=2, is_error=True)) == OrderStatus.FAILED


def test_connect_query_account_positions_orders_trades(broker, fake_api):
    fake_api.orders["o1"] = FakeOrder(
        order_id="o1",
        exchange_id="SHFE",
        instrument_id="rb2610",
        direction="BUY",
        offset="OPEN",
        volume_orign=1,
        volume_left=1,
        status="ALIVE",
        is_error=False,
        exchange_order_id="X1",
    )
    fake_api.trades["t1"] = FakeTrade(
        trade_id="t1",
        order_id="o1",
        exchange_id="SHFE",
        instrument_id="rb2610",
        direction="BUY",
        offset="OPEN",
        price=3500,
        volume=1,
        exchange_trade_id="ET1",
        trade_date_time=1_700_000_000_000_000_000,
    )

    health = broker.connect()
    assert health["broker"] == "tqsdk"
    assert broker.is_connected()
    assert broker.health()["reconciled"] is True

    account = broker.get_account()
    assert account.balance == Decimal("1000000")
    assert account.available_cash == Decimal("800000")
    assert account.curr_margin == Decimal("50000")
    assert "***" in account.account_no

    positions = broker.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "rb2610"
    assert positions[0].direction == "long"
    assert positions[0].quantity == Decimal("2")

    orders = broker.query_orders()
    assert len(orders) == 1
    assert orders[0].status == OrderStatus.SUBMITTED

    trades = broker.query_trades()
    assert len(trades) == 1
    assert trades[0].sdk_trade_id == "t1"
    assert trades[0].raw_payload["broker_type"] == "tqsdk"


def test_live_disabled_blocks_place_allows_cancel(broker, fake_api):
    broker.connect()
    req = PlaceOrderRequest(
        client_order_id="c-1",
        account_id=uuid4(),
        market=Market.FUTURES,
        symbol="rb2610",
        side=OrderSide.BUY,
        action=SignalAction.OPEN,
        price_type=PriceType.LIMIT,
        price=Decimal("3500"),
        quantity=Decimal("1"),
        exchange_id="SHFE",
        offset_flag=OffsetFlag.OPEN,
        hedge_flag=HedgeFlag.SPECULATION,
    )
    with pytest.raises(BrokerConfigurationError):
        broker.place_order(req)

    oid = client_order_id_to_tq_order_id("c-cancel")
    fake_api.orders[oid] = FakeOrder(
        order_id=oid,
        exchange_id="SHFE",
        instrument_id="rb2610",
        direction="BUY",
        offset="OPEN",
        volume_orign=1,
        volume_left=1,
        status="ALIVE",
        is_error=False,
        is_dead=False,
    )
    result = broker.cancel_order(
        CancelOrderRequest(client_order_id="c-cancel", market=Market.FUTURES)
    )
    assert result.status == OrderStatus.CANCELLED


def test_place_order_after_arm(broker, fake_api, monkeypatch):
    monkeypatch.setitem(broker.config, "live_enabled", True)
    broker._live_enabled = True
    broker.connect()
    broker.arm_live_trading("arm-token")

    result = broker.place_order(
        PlaceOrderRequest(
            client_order_id="client_order_abc",
            account_id=uuid4(),
            market=Market.FUTURES,
            symbol="rb2610",
            side=OrderSide.BUY,
            action=SignalAction.OPEN,
            price_type=PriceType.LIMIT,
            price=Decimal("3500"),
            quantity=Decimal("1"),
            exchange_id="SHFE",
            offset_flag=OffsetFlag.OPEN,
        )
    )
    assert result.success is True
    assert result.status == OrderStatus.SUBMITTED
    assert result.sdk_order_id == client_order_id_to_tq_order_id("client_order_abc")


def test_reject_market_and_hedge(broker):
    broker.connect()
    broker._live_enabled = True
    broker._live_armed = True
    with pytest.raises(BrokerSubmitRejected):
        broker.place_order(
            PlaceOrderRequest(
                client_order_id="m1",
                account_id=uuid4(),
                market=Market.FUTURES,
                symbol="rb2610",
                side=OrderSide.BUY,
                action=SignalAction.OPEN,
                price_type=PriceType.MARKET,
                price=None,
                quantity=Decimal("1"),
                exchange_id="SHFE",
                offset_flag=OffsetFlag.OPEN,
            )
        )
    with pytest.raises(BrokerSubmitRejected):
        broker.place_order(
            PlaceOrderRequest(
                client_order_id="h1",
                account_id=uuid4(),
                market=Market.FUTURES,
                symbol="rb2610",
                side=OrderSide.BUY,
                action=SignalAction.OPEN,
                price_type=PriceType.LIMIT,
                price=Decimal("1"),
                quantity=Decimal("1"),
                exchange_id="SHFE",
                offset_flag=OffsetFlag.OPEN,
                hedge_flag=HedgeFlag.HEDGE,
            )
        )


def test_insert_timeout_is_unknown_not_retry(broker, fake_api, monkeypatch):
    monkeypatch.setitem(broker.config, "live_enabled", True)
    broker._live_enabled = True
    broker.connect()
    broker.arm_live_trading("arm-token")

    def sticky_insert(**kwargs):
        oid = kwargs.get("order_id") or "sticky"
        order = FakeOrder(
            order_id=oid,
            exchange_id="SHFE",
            instrument_id="rb2610",
            direction=kwargs["direction"],
            offset=kwargs["offset"],
            volume_orign=int(kwargs["volume"]),
            volume_left=int(kwargs["volume"]),
            limit_price=kwargs.get("limit_price"),
            status="",  # 永不确认
            is_error=False,
            is_dead=False,
            last_msg="",
        )
        fake_api.orders[oid] = order
        return order

    fake_api.insert_order = sticky_insert
    fake_api.wait_update = lambda deadline=None: time.sleep(0.01) or True
    broker._runtime.config["command_timeout_seconds"] = 0.25
    broker._runtime._timeout = 0.25

    with pytest.raises(BrokerSubmitOutcomeUnknown):
        broker.place_order(
            PlaceOrderRequest(
                client_order_id="timeout-1",
                account_id=uuid4(),
                market=Market.FUTURES,
                symbol="rb2610",
                side=OrderSide.BUY,
                action=SignalAction.OPEN,
                price_type=PriceType.LIMIT,
                price=Decimal("3500"),
                quantity=Decimal("1"),
                exchange_id="SHFE",
                offset_flag=OffsetFlag.OPEN,
            )
        )


def test_manager_routes_tqsdk(monkeypatch):
    broker_manager.reset_brokers()
    monkeypatch.setattr(settings, "futures_broker_type", "tqsdk")
    monkeypatch.setattr(settings, "tqsdk_broker_id", "faka")
    monkeypatch.setattr(settings, "tqsdk_account_id", "12345678")
    monkeypatch.setattr(settings, "tqsdk_password", "x")
    monkeypatch.setattr(settings, "tqsdk_auth_user", "u")
    monkeypatch.setattr(settings, "tqsdk_auth_password", "p")
    broker = broker_manager.get_broker(Market.FUTURES)
    assert isinstance(broker, TqSdkBroker)
    assert broker.name == "tqsdk"
    assert broker.config["broker_id"] == "faka"
    broker_manager.reset_brokers()


def test_futures_channel_readiness_tqsdk(monkeypatch, broker):
    from app.services.futures_channel_service import futures_channel_readiness

    monkeypatch.setattr(
        "app.services.futures_channel_service.broker_manager.get_broker",
        lambda market: broker,
    )
    ready, reason = futures_channel_readiness()
    assert ready is False
    assert "TqSdk" in reason

    broker.connect()
    ready, reason = futures_channel_readiness()
    assert ready is True
    assert reason == ""
