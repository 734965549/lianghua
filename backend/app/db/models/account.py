from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, RawPayloadMixin, TimestampMixin, UUIDPrimaryKey, pg_enum
from app.schemas.enums import AccountStatus, Market


class Account(Base, UUIDPrimaryKey, TimestampMixin, RawPayloadMixin):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("market", "account_no", name="uk_accounts_market_no"),)

    account_no: Mapped[str] = mapped_column(String(64), nullable=False)
    account_name: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    market: Mapped[Market] = mapped_column(pg_enum(Market, "market_type"), nullable=False)
    broker_name: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    sdk_account_ref: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    status: Mapped[AccountStatus] = mapped_column(
        pg_enum(AccountStatus, "account_status_type"),
        nullable=False,
        server_default=AccountStatus.ACTIVE.value,
    )
