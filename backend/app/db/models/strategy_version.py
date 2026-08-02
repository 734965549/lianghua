from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKey


class StrategyVersion(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uk_strategy_versions_id_ver"),
    )

    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    parameters_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    change_note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
