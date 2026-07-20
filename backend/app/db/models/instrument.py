from sqlalchemy import Boolean, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, RawPayloadMixin, TimestampMixin, UUIDPrimaryKey, pg_enum
from app.schemas.enums import Market


class Instrument(Base, UUIDPrimaryKey, TimestampMixin, RawPayloadMixin):
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("market", "symbol", name="uk_instruments_market_symbol"),)

    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[Market] = mapped_column(pg_enum(Market, "market_type"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, server_default="")
    price_tick: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, server_default="0")
    lot_size: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, server_default="1")
    multiplier: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
