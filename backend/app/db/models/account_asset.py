import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, RawPayloadMixin, UUIDPrimaryKey


class AccountAsset(Base, UUIDPrimaryKey, RawPayloadMixin):
    __tablename__ = "account_assets"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    total_asset: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    available_cash: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    frozen_cash: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    market_value: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    pnl: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="0")
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
