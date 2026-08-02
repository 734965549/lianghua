from decimal import Decimal
from uuid import uuid4

import pytest

from app.schemas.enums import Market, OrderSide, PriceType, SignalAction
from app.sdk.matching import limit_safe_fill_price
from app.sdk.models import PlaceOrderRequest


def _request(side: OrderSide, price: str) -> PlaceOrderRequest:
    return PlaceOrderRequest(
        client_order_id=f"limit-{side.value}",
        account_id=uuid4(),
        market=Market.STOCK,
        symbol="600000.SH",
        side=side,
        action=SignalAction.OPEN if side == OrderSide.BUY else SignalAction.CLOSE,
        price_type=PriceType.LIMIT,
        price=Decimal(price),
        quantity=Decimal("100"),
    )


@pytest.mark.unit
def test_limit_safe_fill_price_enforces_buy_and_sell_bounds():
    assert limit_safe_fill_price(
        _request(OrderSide.BUY, "10.00"), Decimal("10.06")
    ) == Decimal("10.00")
    assert limit_safe_fill_price(
        _request(OrderSide.SELL, "11.47"), Decimal("10.05")
    ) == Decimal("11.47")
