"""watchlist and data_sync_log tables

Revision ID: 0009_data_layer
Revises: 0008_audit_append_only
Create Date: 2026-07-28

数据层改造：股票池配置 + 下载任务日志。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_data_layer"
down_revision: Union[str, None] = "0008_audit_append_only"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

market_type = postgresql.ENUM("stock", "futures", name="market_type", create_type=False)


def upgrade() -> None:
    op.create_table(
        "watchlist",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("market", market_type, nullable=False),
        sa.Column("alias", sa.String(50), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("download_1d", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("download_1m", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("market", "symbol", name="uk_watchlist_market_symbol"),
    )
    op.create_index("idx_watchlist_enabled", "watchlist", ["enabled"])
    op.execute("COMMENT ON TABLE watchlist IS '股票池 / 标的订阅配置'")

    op.create_table(
        "data_sync_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_type", sa.String(32), nullable=False, server_default="download"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("symbols", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("intervals", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("start_date", sa.String(16), nullable=True),
        sa.Column("end_date", sa.String(16), nullable=True),
        sa.Column("progress", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_data_sync_log_status", "data_sync_log", ["status", "created_at"])
    op.execute("COMMENT ON TABLE data_sync_log IS '历史数据下载 / 同步任务日志'")


def downgrade() -> None:
    op.drop_index("idx_data_sync_log_status", table_name="data_sync_log")
    op.drop_table("data_sync_log")
    op.drop_index("idx_watchlist_enabled", table_name="watchlist")
    op.drop_table("watchlist")
