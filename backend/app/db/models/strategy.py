from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Strategy(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "strategies"
    __table_args__ = (UniqueConstraint("strategy_id", name="uk_strategies_id"),)

    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    supported_markets: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="builtin")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="published")
    current_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    definition_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
