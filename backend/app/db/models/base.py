import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def pg_enum(enum_class: type[PyEnum], name: str) -> Enum:
    """PostgreSQL 原生枚举，存储 Python Enum 的 value（小写字符串）。"""
    return Enum(
        enum_class,
        name=name,
        native_enum=True,
        create_constraint=False,
        values_callable=lambda x: [e.value for e in x],
    )


class TimestampMixin:
    """通用时间戳 mixin。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RawPayloadMixin:
    """SDK 原始返回 mixin。"""

    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class UUIDPrimaryKey:
    """UUID 主键 mixin。"""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
