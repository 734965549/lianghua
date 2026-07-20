"""orders, trades, positions, account_assets

Revision ID: 0005_orders_trades
Revises: 0004_strategy_risk
Create Date: 2026-07-20

阶段 4：订单、成交、持仓、资金快照；若无账户则插入 Mock 默认账户。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_orders_trades"
down_revision: Union[str, None] = "0004_strategy_risk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

market_type = postgresql.ENUM("stock", "futures", name="market_type", create_type=False)
order_side_type = postgresql.ENUM("buy", "sell", name="order_side_type", create_type=False)
signal_action_type = postgresql.ENUM(
    "open", "close", "reduce", "increase", name="signal_action_type", create_type=False
)
price_type = postgresql.ENUM("limit", "market", name="price_type", create_type=False)
order_status_type = postgresql.ENUM(
    "pending_risk",
    "risk_rejected",
    "submitting",
    "submitted",
    "partially_filled",
    "filled",
    "cancelled",
    "failed",
    "unknown",
    name="order_status_type",
    create_type=False,
)
account_status_type = postgresql.ENUM("active", "disabled", name="account_status_type", create_type=False)


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_order_id", sa.String(64), nullable=False),
        sa.Column("sdk_order_id", sa.String(128), nullable=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("strategy_id", sa.String(64), nullable=True),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("market", market_type, nullable=False),
        sa.Column("side", order_side_type, nullable=False),
        sa.Column("action", signal_action_type, nullable=False),
        sa.Column("price_type", price_type, nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("filled_quantity", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("status", order_status_type, nullable=False, server_default="pending_risk"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fail_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("client_order_id", name="uk_orders_client_id"),
    )
    op.create_index(
        "uk_orders_sdk_id",
        "orders",
        ["market", "sdk_order_id"],
        unique=True,
        postgresql_where=sa.text("sdk_order_id IS NOT NULL"),
    )
    op.create_index(
        "idx_orders_status",
        "orders",
        ["status", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index(
        "idx_orders_strategy",
        "orders",
        ["strategy_id", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index(
        "idx_orders_symbol",
        "orders",
        ["market", "symbol", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )
    op.execute("COMMENT ON TABLE orders IS '委托订单'")

    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sdk_trade_id", sa.String(128), nullable=False),
        sa.Column("client_order_id", sa.String(64), nullable=False),
        sa.Column("sdk_order_id", sa.String(128), nullable=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("strategy_id", sa.String(64), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("market", market_type, nullable=False),
        sa.Column("side", order_side_type, nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("fee", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("trade_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("market", "sdk_trade_id", name="uk_trades_sdk_id"),
    )
    op.create_index("idx_trades_order", "trades", ["client_order_id"])
    op.create_index(
        "idx_trades_time",
        "trades",
        ["trade_time"],
        postgresql_ops={"trade_time": "DESC"},
    )
    op.create_index(
        "idx_trades_symbol",
        "trades",
        ["market", "symbol", "trade_time"],
        postgresql_ops={"trade_time": "DESC"},
    )
    op.execute("COMMENT ON TABLE trades IS '成交记录'")

    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("market", market_type, nullable=False),
        sa.Column("direction", sa.String(16), nullable=False, server_default="net"),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("available_quantity", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("avg_cost", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("market_value", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("pnl", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_positions_lookup",
        "positions",
        ["account_id", "market", "symbol", "snapshot_time"],
        postgresql_ops={"snapshot_time": "DESC"},
    )
    op.execute("COMMENT ON TABLE positions IS '持仓快照'")

    op.create_table(
        "account_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("total_asset", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("available_cash", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("frozen_cash", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("market_value", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("pnl", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_assets_lookup",
        "account_assets",
        ["account_id", "snapshot_time"],
        postgresql_ops={"snapshot_time": "DESC"},
    )
    op.execute("COMMENT ON TABLE account_assets IS '账户资金快照'")

    op.execute(
        """
        INSERT INTO accounts (account_no, account_name, market, broker_name, sdk_account_ref, status)
        SELECT 'MOCK001_STOCK', 'Mock 股票账户', 'stock', 'Mock', 'MOCK_STOCK', 'active'
        WHERE NOT EXISTS (SELECT 1 FROM accounts WHERE market = 'stock')
        """
    )
    op.execute(
        """
        INSERT INTO accounts (account_no, account_name, market, broker_name, sdk_account_ref, status)
        SELECT 'MOCK001_FUTURES', 'Mock 期货账户', 'futures', 'Mock', 'MOCK_FUTURES', 'active'
        WHERE NOT EXISTS (SELECT 1 FROM accounts WHERE market = 'futures')
        """
    )


def downgrade() -> None:
    op.drop_index("idx_assets_lookup", table_name="account_assets")
    op.drop_table("account_assets")
    op.drop_index("idx_positions_lookup", table_name="positions")
    op.drop_table("positions")
    op.drop_index("idx_trades_symbol", table_name="trades")
    op.drop_index("idx_trades_time", table_name="trades")
    op.drop_index("idx_trades_order", table_name="trades")
    op.drop_table("trades")
    op.drop_index("idx_orders_symbol", table_name="orders")
    op.drop_index("idx_orders_strategy", table_name="orders")
    op.drop_index("idx_orders_status", table_name="orders")
    op.drop_index("uk_orders_sdk_id", table_name="orders")
    op.drop_table("orders")
