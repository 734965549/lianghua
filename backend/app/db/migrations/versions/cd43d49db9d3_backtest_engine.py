"""backtest engine

Revision ID: cd43d49db9d3
Revises: 0009_data_layer
Create Date: 2026-07-29 19:20:37.271761

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "cd43d49db9d3"
down_revision: Union[str, None] = "0009_data_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 幂等创建枚举类型，避免数据库已残留同名类型时报 duplicate key
    op.execute(
        "CREATE TYPE IF NOT EXISTS backtest_status AS ENUM ('pending', 'running', 'completed', 'failed')"
    )
    op.create_table(
        "backtest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("strategy_id", sa.String(64), nullable=False, index=True),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("symbols", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("granularity", sa.String(32), nullable=False),
        sa.Column("fill_model", sa.String(32), nullable=False),
        sa.Column("initial_cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("final_equity", sa.Numeric(24, 8), nullable=True),
        sa.Column("metrics_json", postgresql.JSONB(), nullable=True),
        sa.Column("trades_json", postgresql.JSONB(), nullable=True),
        sa.Column("equity_curve_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", name="backtest_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("COMMENT ON TABLE backtest_runs IS '回测任务记录'")


def downgrade() -> None:
    op.drop_table("backtest_runs")
    op.execute("DROP TYPE IF EXISTS backtest_status")
