from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, pg_enum
from app.schemas.enums import SystemStatus


class SystemState(Base):
    __tablename__ = "system_state"
    __table_args__ = (CheckConstraint("id = 1", name="chk_system_state_singleton"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    status: Mapped[SystemStatus] = mapped_column(
        pg_enum(SystemStatus, "system_status_type"),
        nullable=False,
        server_default=SystemStatus.INITIALIZING.value,
    )
    status_reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
