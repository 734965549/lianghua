from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Numeric, SmallInteger, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class RiskConfig(Base):
    __tablename__ = "risk_configs"
    __table_args__ = (CheckConstraint("id = 1", name="chk_risk_configs_singleton"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    allowed_symbols: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    blocked_symbols: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    trading_sessions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    max_order_amount: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="1000000")
    max_order_quantity: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="10000")
    max_symbol_position: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="100000")
    max_total_position: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="1000000")
    daily_loss_limit: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False, server_default="50000")
    daily_trade_count_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    sdk_disconnect_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    quote_stale_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    consecutive_order_fail_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    duplicate_signal_window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    auto_cancel_on_breaker: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
