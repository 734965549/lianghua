from datetime import datetime

from sqlalchemy import Boolean, DateTime, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, UUIDPrimaryKey


class SystemConfig(Base, UUIDPrimaryKey):
    __tablename__ = "system_configs"
    __table_args__ = (UniqueConstraint("config_key", name="uk_system_configs_key"),)

    config_key: Mapped[str] = mapped_column(String(128), nullable=False)
    config_value: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    encrypted_value: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
