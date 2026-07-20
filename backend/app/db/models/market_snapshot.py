import uuid
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, pg_enum
from app.schemas.enums import Market


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[Market] = mapped_column(pg_enum(Market, "market_type"), nullable=False)
    quote_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    change_rate: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, server_default="0")
    volume: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    bid_price: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    ask_price: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    bid_volume: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    ask_volume: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
