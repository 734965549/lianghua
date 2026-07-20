import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, RawPayloadMixin, UUIDPrimaryKey, pg_enum
from app.schemas.enums import Market, OrderSide


class Trade(Base, UUIDPrimaryKey, RawPayloadMixin):
    __tablename__ = "trades"
    __table_args__ = (UniqueConstraint("market", "sdk_trade_id", name="uk_trades_sdk_id"),)

    sdk_trade_id: Mapped[str] = mapped_column(String(128), nullable=False)
    client_order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sdk_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[Market] = mapped_column(pg_enum(Market, "market_type"), nullable=False)
    side: Mapped[OrderSide] = mapped_column(pg_enum(OrderSide, "order_side_type"), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    fee: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, server_default="0")
    trade_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
