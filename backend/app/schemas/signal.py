from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.enums import Market, OrderSide, PriceType, SignalAction


class TradeSignal(BaseModel):
    signal_id: UUID
    strategy_id: str
    symbol: str
    market: Market
    side: OrderSide
    action: SignalAction
    price_type: PriceType
    price: Decimal | None = None
    quantity: Decimal
    reason: str = ""
    signal_time: datetime
    metadata: dict = {}
