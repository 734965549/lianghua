from pydantic import BaseModel, Field

from app.schemas.enums import Market


class QuoteSubscriptionRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)
    market: Market
