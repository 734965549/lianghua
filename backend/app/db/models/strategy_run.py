import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, pg_enum
from app.schemas.enums import StrategyRunStatus


class StrategyRun(Base, TimestampMixin):
    __tablename__ = "strategy_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[StrategyRunStatus] = mapped_column(
        pg_enum(StrategyRunStatus, "strategy_run_status_type"),
        nullable=False,
        server_default=StrategyRunStatus.PENDING_CONFIRM.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
