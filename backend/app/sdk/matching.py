"""模拟撮合的价格约束。"""

from decimal import Decimal

from app.schemas.enums import OrderSide, PriceType
from app.sdk.models import PlaceOrderRequest


def limit_safe_fill_price(request: PlaceOrderRequest, candidate: Decimal) -> Decimal:
    """将候选成交价约束在限价委托允许的价格范围内。"""
    candidate = Decimal(str(candidate))
    if (
        request.price_type != PriceType.LIMIT
        or request.price is None
        or request.price <= 0
    ):
        return candidate

    limit_price = Decimal(str(request.price))
    if request.side == OrderSide.BUY:
        return min(candidate, limit_price)
    if request.side == OrderSide.SELL:
        return max(candidate, limit_price)
    return candidate
