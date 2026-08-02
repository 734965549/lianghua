from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.backtest.account import SimulationAccount
from app.backtest.broker import SimulationBroker
from app.backtest.data_source import MarketEvent
from app.backtest.fill_model import FillModelEngine
from app.backtest.models import BacktestOrderRequest
from app.schemas.enums import FillModel, Market, OrderSide, PriceType
from app.sdk.models import KlineBar


@pytest.fixture
def broker() -> SimulationBroker:
    account = SimulationAccount(initial_cash=Decimal("100000"))
    fill_model = FillModelEngine(FillModel.NEXT_CLOSE)
    from app.services.cost_service import CostService

    cost_service = CostService(
        commission_rate=Decimal("0.0003"),
        stamp_tax_rate=Decimal("0.001"),
    )
    return SimulationBroker(
        account=account,
        fill_model=fill_model,
        cost_service=cost_service,
    )


def make_event(symbol: str, close: Decimal, event_time: datetime | None = None) -> MarketEvent:
    return MarketEvent(
        event_time=event_time or datetime(2024, 1, 1, tzinfo=timezone.utc),
        symbol=symbol,
        bar=KlineBar(
            symbol=symbol,
            market=Market.STOCK,
            interval="1d",
            bar_time=event_time or datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=close,
            high=close + Decimal("1"),
            low=close - Decimal("1"),
            close=close,
            volume=Decimal("1000"),
        ),
    )


def test_submit_order(broker: SimulationBroker) -> None:
    order = BacktestOrderRequest(
        client_order_id="o1",
        symbol="600519.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        price_type=PriceType.MARKET,
        quantity=Decimal("100"),
    )
    cid = broker.submit_order(order)
    assert cid == "o1"
    assert len(broker._pending) == 1


def test_market_buy_fill(broker: SimulationBroker) -> None:
    order = BacktestOrderRequest(
        client_order_id="o1",
        symbol="600519.SH",
        market=Market.STOCK,
        side=OrderSide.BUY,
        price_type=PriceType.MARKET,
        quantity=Decimal("100"),
    )
    broker.submit_order(order)
    event = make_event("600519.SH", Decimal("100"))
    fills = broker.on_market_event(event)
    assert len(fills) == 1
    fill = fills[0]
    assert fill.symbol == "600519.SH"
    assert fill.side == OrderSide.BUY
    assert fill.quantity == Decimal("100")
    assert fill.price == Decimal("100")
    assert fill.commission > Decimal("0")
    assert broker.account.get_position("600519.SH") is not None


def test_limit_sell_fill(broker: SimulationBroker) -> None:
    # 先买入
    broker.submit_order(
        BacktestOrderRequest(
            client_order_id="o1",
            symbol="600519.SH",
            market=Market.STOCK,
            side=OrderSide.BUY,
            price_type=PriceType.MARKET,
            quantity=Decimal("100"),
        )
    )
    broker.on_market_event(make_event("600519.SH", Decimal("100")))

    # 限价卖出，价格>=100 时成交
    broker.submit_order(
        BacktestOrderRequest(
            client_order_id="o2",
            symbol="600519.SH",
            market=Market.STOCK,
            side=OrderSide.SELL,
            price_type=PriceType.LIMIT,
            quantity=Decimal("100"),
            price=Decimal("105"),
        )
    )
    fills = broker.on_market_event(make_event("600519.SH", Decimal("110")))
    assert len(fills) == 1
    assert fills[0].side == OrderSide.SELL
    pos = broker.account.get_position("600519.SH")
    assert pos is not None
    assert pos.quantity == Decimal("0")


def test_order_update_callback(broker: SimulationBroker) -> None:
    events: list = []
    broker._order_update_callback = lambda ev: events.append(ev)

    broker.submit_order(
        BacktestOrderRequest(
            client_order_id="o1",
            symbol="600519.SH",
            market=Market.STOCK,
            side=OrderSide.BUY,
            price_type=PriceType.MARKET,
            quantity=Decimal("100"),
        )
    )
    broker.on_market_event(make_event("600519.SH", Decimal("100")))
    assert len(events) == 1
    assert events[0].status.value == "filled"


def test_partial_fill_not_supported_yet(broker: SimulationBroker) -> None:
    """当前实现一次性全部成交；此测试用于锁定该行为。"""
    broker.submit_order(
        BacktestOrderRequest(
            client_order_id="o1",
            symbol="600519.SH",
            market=Market.STOCK,
            side=OrderSide.BUY,
            price_type=PriceType.MARKET,
            quantity=Decimal("100"),
        )
    )
    fills = broker.on_market_event(make_event("600519.SH", Decimal("100")))
    assert fills[0].quantity == Decimal("100")
    assert broker._pending == []
