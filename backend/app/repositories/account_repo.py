from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.models.account import Account
from app.repositories.base import BaseRepository
from app.schemas.enums import AccountStatus, Market

DEFAULT_ACCOUNTS: dict[Market, dict[str, str]] = {
    Market.STOCK: {
        "account_no": "MOCK001_STOCK",
        "account_name": "Mock 股票账户",
        "broker_name": "Mock",
        "sdk_account_ref": "MOCK_STOCK",
    },
    Market.FUTURES: {
        "account_no": "MOCK001_FUTURES",
        "account_name": "Mock 期货账户",
        "broker_name": "Mock",
        "sdk_account_ref": "MOCK_FUTURES",
    },
}


class AccountRepository(BaseRepository[Account]):
    model = Account

    def get_by_market(self, market: Market) -> Account | None:
        return (
            self.db.query(Account)
            .filter(Account.market == market, Account.status == AccountStatus.ACTIVE)
            .order_by(Account.created_at)
            .first()
        )

    def get_or_create_default(self, market: Market) -> Account:
        row = self.get_by_market(market)
        if row is not None:
            return row
        cfg = DEFAULT_ACCOUNTS[market]
        row = Account(
            account_no=cfg["account_no"],
            account_name=cfg["account_name"],
            market=market,
            broker_name=cfg["broker_name"],
            sdk_account_ref=cfg["sdk_account_ref"],
            status=AccountStatus.ACTIVE,
        )
        return self.add(row)

    def get_by_id(self, account_id: UUID) -> Account | None:
        return self.db.get(Account, account_id)
