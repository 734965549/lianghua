from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    object_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    request_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    operator: Mapped[str] = mapped_column(String(64), nullable=False, server_default="local_user")
