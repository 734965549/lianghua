from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKey, pg_enum
from app.schemas.enums import BacktestStatus


class BacktestRun(Base, UUIDPrimaryKey, TimestampMixin):
    """回测任务记录，包含请求参数与结果。"""

    __tablename__ = "backtest_runs"

    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    symbols: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    granularity: Mapped[str] = mapped_column(String(32), nullable=False)
    fill_model: Mapped[str] = mapped_column(String(32), nullable=False)
    initial_cash: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    final_equity: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    trades_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    equity_curve_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[BacktestStatus] = mapped_column(
        pg_enum(BacktestStatus, "backtest_status"),
        nullable=False,
        server_default=BacktestStatus.PENDING.value,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
