import uuid
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, pg_enum
from app.schemas.enums import Market, OrderSide, PriceType, SignalAction


class StrategySignal(Base):
    __tablename__ = "strategy_signals"

    signal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[Market] = mapped_column(pg_enum(Market, "market_type"), nullable=False)
    side: Mapped[OrderSide] = mapped_column(pg_enum(OrderSide, "order_side_type"), nullable=False)
    action: Mapped[SignalAction] = mapped_column(pg_enum(SignalAction, "signal_action_type"), nullable=False)
    price_type: Mapped[PriceType] = mapped_column(pg_enum(PriceType, "price_type"), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, server_default="0")
    quantity: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    signal_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
