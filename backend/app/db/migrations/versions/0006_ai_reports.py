"""ai_reports table for phase 7

Revision ID: 0006_ai_reports
Revises: 0005_orders_trades
Create Date: 2026-07-20

阶段 7：AI 复盘报告表。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_ai_reports"
down_revision: Union[str, None] = "0005_orders_trades"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_reports",
        sa.Column("report_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("range_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("range_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_format", sa.String(16), nullable=False, server_default="markdown"),
        sa.Column("model_name", sa.String(128), nullable=False, server_default="rule_based"),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_ai_reports_time", "ai_reports", ["range_start"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_ai_reports_time", table_name="ai_reports")
    op.drop_table("ai_reports")
