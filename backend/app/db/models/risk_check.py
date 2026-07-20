import uuid
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, pg_enum
from app.schemas.enums import RiskResult


class RiskCheck(Base):
    __tablename__ = "risk_checks"

    check_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    client_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[RiskResult] = mapped_column(pg_enum(RiskResult, "risk_result_type"), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
