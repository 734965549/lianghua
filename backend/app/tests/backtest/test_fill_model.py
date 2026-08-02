from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.backtest.data_source import MarketEvent
from app.backtest.fill_model import FillModelEngine
from app.backtest.models import BacktestOrderRequest
from app.schemas.enums import FillModel, Market, OrderSide, PriceType
from app.sdk.models import KlineBar, QuoteSnapshot


def make_bar(close: Decimal, open_p: Decimal | None = None) -> KlineBar:
    return KlineBar(
        symbol="600519.SH",
        market=Market.STOCK,
        interval="1d",
        bar_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=open_p or close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("1000"),
    )


def make_event(bar: KlineBar | None = None, quote: QuoteSnapshot | None = None) -> MarketEvent:
    return MarketEvent(
        event_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        symbol="600519.SH",
        bar=bar,
        quote=quote,
    )


def make_order(side: OrderSide, price_type: PriceType, price: Decimal | None = None) -> BacktestOrderRequest:
    return BacktestOrderRequest(
        client_order_id="t1",
        symbol="600519.SH",
        market=Market.STOCK,
        side=side,
        price_type=price_type,
        quantity=Decimal("100"),
        price=price,
    )


def test_next_open_fill() -> None:
    engine = FillModelEngine(FillModel.NEXT_OPEN)
    bar = make_bar(close=Decimal("100"), open_p=Decimal("99"))
    result = engine.can_fill(make_order(OrderSide.BUY, PriceType.MARKET), make_event(bar=bar))
    assert result is not None
    assert result.price == Decimal("99")


def test_next_close_fill() -> None:
    engine = FillModelEngine(FillModel.NEXT_CLOSE)
    bar = make_bar(close=Decimal("100"), open_p=Decimal("99"))
    result = engine.can_fill(make_order(OrderSide.BUY, PriceType.MARKET), make_event(bar=bar))
    assert result is not None
    assert result.price == Decimal("100")


def test_vwap_fill() -> None:
    engine = FillModelEngine(FillModel.VWAP)
    bar = KlineBar(
        symbol="600519.SH",
        market=Market.STOCK,
        interval="1d",
        bar_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=Decimal("98"),
        high=Decimal("102"),
        low=Decimal("97"),
        close=Decimal("101"),
        volume=Decimal("1000"),
    )
    result = engine.can_fill(make_order(OrderSide.BUY, PriceType.MARKET), make_event(bar=bar))
    assert result is not None
    assert result.price == (Decimal("98") + Decimal("102") + Decimal("97") + Decimal("101")) / Decimal("4")


def test_limit_buy_fill_when_price_below_limit() -> None:
    engine = FillModelEngine(FillModel.NEXT_CLOSE)
    bar = make_bar(close=Decimal("95"))
    order = make_order(OrderSide.BUY, PriceType.LIMIT, Decimal("100"))
    result = engine.can_fill(order, make_event(bar=bar))
    assert result is not None
    assert result.price == Decimal("95")


def test_limit_buy_not_fill_when_price_above_limit() -> None:
    engine = FillModelEngine(FillModel.NEXT_CLOSE)
    bar = make_bar(close=Decimal("105"))
    order = make_order(OrderSide.BUY, PriceType.LIMIT, Decimal("100"))
    result = engine.can_fill(order, make_event(bar=bar))
    assert result is None


def test_slippage_applied_to_market_order() -> None:
    engine = FillModelEngine(FillModel.NEXT_CLOSE, slippage=Decimal("0.001"))
    bar = make_bar(close=Decimal("100"))
    result = engine.can_fill(make_order(OrderSide.BUY, PriceType.MARKET), make_event(bar=bar))
    assert result is not None
    assert result.price == Decimal("100.1")

    result_sell = engine.can_fill(make_order(OrderSide.SELL, PriceType.MARKET), make_event(bar=bar))
    assert result_sell is not None
    assert result_sell.price == Decimal("99.9")


def test_quote_fill() -> None:
    engine = FillModelEngine(FillModel.TICK_PRICE)
    quote = QuoteSnapshot(
        symbol="600519.SH",
        market=Market.STOCK,
        last_price=Decimal("100"),
        quote_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    result = engine.can_fill(make_order(OrderSide.BUY, PriceType.MARKET), make_event(quote=quote))
    assert result is not None
    assert result.price == Decimal("100")
