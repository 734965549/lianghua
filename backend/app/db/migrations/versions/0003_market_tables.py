"""market snapshots and kline bars

Revision ID: 0003_market_tables
Revises: 0002_phase1_core
Create Date: 2026-07-20

阶段 2：行情快照、K 线表。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_market_tables"
down_revision: Union[str, None] = "0002_phase1_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

market_type = postgresql.ENUM("stock", "futures", name="market_type", create_type=False)


def upgrade() -> None:
    op.create_table(
        "market_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("market", market_type, nullable=False),
        sa.Column("quote_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("change_rate", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("volume", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("bid_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("ask_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("bid_volume", sa.Numeric(24, 8), nullable=True),
        sa.Column("ask_volume", sa.Numeric(24, 8), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_market_snapshots_lookup",
        "market_snapshots",
        ["market", "symbol", "quote_time"],
        postgresql_ops={"quote_time": "DESC"},
    )
    op.execute("COMMENT ON TABLE market_snapshots IS '实时行情快照'")

    op.create_table(
        "kline_bars",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("market", market_type, nullable=False),
        sa.Column("interval", sa.String(16), nullable=False),
        sa.Column("bar_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(20, 8), nullable=False),
        sa.Column("high", sa.Numeric(20, 8), nullable=False),
        sa.Column("low", sa.Numeric(20, 8), nullable=False),
        sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("volume", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("market", "symbol", "interval", "bar_time", name="uk_kline_bars"),
    )
    op.create_index(
        "idx_kline_bars_lookup",
        "kline_bars",
        ["market", "symbol", "interval", "bar_time"],
        postgresql_ops={"bar_time": "DESC"},
    )
    op.execute("COMMENT ON TABLE kline_bars IS '历史 K 线'")


def downgrade() -> None:
    op.drop_index("idx_kline_bars_lookup", table_name="kline_bars")
    op.drop_table("kline_bars")
    op.drop_index("idx_market_snapshots_lookup", table_name="market_snapshots")
    op.drop_table("market_snapshots")
