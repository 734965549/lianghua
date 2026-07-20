import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, RawPayloadMixin, UUIDPrimaryKey, pg_enum
from app.schemas.enums import Market


class Position(Base, UUIDPrimaryKey, RawPayloadMixin):
    __tablename__ = "positions"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[Market] = mapped_column(pg_enum(Market, "market_type"), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, server_default="net")
    quantity: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    available_quantity: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    avg_cost: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, server_default="0")
    market_value: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    pnl: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
