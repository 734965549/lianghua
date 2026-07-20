import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, RawPayloadMixin, TimestampMixin, UUIDPrimaryKey, pg_enum
from app.schemas.enums import Market, OrderSide, OrderStatus, PriceType, SignalAction


class Order(Base, UUIDPrimaryKey, TimestampMixin, RawPayloadMixin):
    __tablename__ = "orders"

    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    sdk_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[Market] = mapped_column(pg_enum(Market, "market_type"), nullable=False)
    side: Mapped[OrderSide] = mapped_column(pg_enum(OrderSide, "order_side_type"), nullable=False)
    action: Mapped[SignalAction] = mapped_column(pg_enum(SignalAction, "signal_action_type"), nullable=False)
    price_type: Mapped[PriceType] = mapped_column(pg_enum(PriceType, "price_type"), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, server_default="0")
    quantity: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    filled_quantity: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    status: Mapped[OrderStatus] = mapped_column(
        pg_enum(OrderStatus, "order_status_type"),
        nullable=False,
        server_default=OrderStatus.PENDING_RISK.value,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fail_reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
