"""strategy and risk tables

Revision ID: 0004_strategy_risk
Revises: 0003_market_tables
Create Date: 2026-07-20

阶段 3：策略定义/运行/信号、风控配置与检查记录。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_strategy_risk"
down_revision: Union[str, None] = "0003_market_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

market_type = postgresql.ENUM("stock", "futures", name="market_type", create_type=False)
order_side_type = postgresql.ENUM("buy", "sell", name="order_side_type", create_type=False)
signal_action_type = postgresql.ENUM(
    "open", "close", "reduce", "increase", name="signal_action_type", create_type=False
)
price_type = postgresql.ENUM("limit", "market", name="price_type", create_type=False)
strategy_run_status_type = postgresql.ENUM(
    "running", "paused", "stopped", "failed", "pending_confirm",
    name="strategy_run_status_type",
    create_type=False,
)
risk_result_type = postgresql.ENUM("passed", "rejected", "warning", name="risk_result_type", create_type=False)


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("strategy_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("supported_markets", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("strategy_id", name="uk_strategies_id"),
    )
    op.execute("COMMENT ON TABLE strategies IS '策略定义'")

    op.create_table(
        "strategy_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("strategy_id", sa.String(64), nullable=False),
        sa.Column("status", strategy_run_status_type, nullable=False, server_default="pending_confirm"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_strategy_runs_strategy",
        "strategy_runs",
        ["strategy_id", "started_at"],
        postgresql_ops={"started_at": "DESC"},
    )
    op.execute("COMMENT ON TABLE strategy_runs IS '策略运行实例'")

    op.create_table(
        "strategy_signals",
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("strategy_id", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("market", market_type, nullable=False),
        sa.Column("side", order_side_type, nullable=False),
        sa.Column("action", signal_action_type, nullable=False),
        sa.Column("price_type", price_type, nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("signal_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_signals_strategy",
        "strategy_signals",
        ["strategy_id", "signal_time"],
        postgresql_ops={"signal_time": "DESC"},
    )
    op.create_index(
        "idx_signals_symbol",
        "strategy_signals",
        ["market", "symbol", "signal_time"],
        postgresql_ops={"signal_time": "DESC"},
    )
    op.execute("COMMENT ON TABLE strategy_signals IS '策略信号'")

    op.create_table(
        "risk_configs",
        sa.Column("id", sa.SmallInteger(), primary_key=True, server_default="1"),
        sa.Column("allowed_symbols", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("blocked_symbols", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("trading_sessions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("max_order_amount", sa.Numeric(24, 8), nullable=False, server_default="1000000"),
        sa.Column("max_order_quantity", sa.Numeric(24, 8), nullable=False, server_default="10000"),
        sa.Column("max_symbol_position", sa.Numeric(24, 8), nullable=False, server_default="100000"),
        sa.Column("max_total_position", sa.Numeric(24, 8), nullable=False, server_default="1000000"),
        sa.Column("daily_loss_limit", sa.Numeric(24, 8), nullable=False, server_default="50000"),
        sa.Column("daily_trade_count_limit", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("sdk_disconnect_timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("quote_stale_timeout_seconds", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("consecutive_order_fail_limit", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("duplicate_signal_window_seconds", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("auto_cancel_on_breaker", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("id = 1", name="chk_risk_configs_singleton"),
    )
    op.execute("COMMENT ON TABLE risk_configs IS '风控配置（单行）'")

    op.create_table(
        "risk_checks",
        sa.Column("check_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_order_id", sa.String(64), nullable=True),
        sa.Column("result", risk_result_type, nullable=False),
        sa.Column("rule_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index(
        "idx_risk_checks_time",
        "risk_checks",
        ["checked_at"],
        postgresql_ops={"checked_at": "DESC"},
    )
    op.create_index("idx_risk_checks_order", "risk_checks", ["client_order_id"])
    op.create_index("idx_risk_checks_signal", "risk_checks", ["signal_id"])
    op.execute("COMMENT ON TABLE risk_checks IS '风控检查记录'")

    op.execute(
        """
        INSERT INTO risk_configs (
            id, allowed_symbols, blocked_symbols, trading_sessions
        ) VALUES (
            1,
            '["600000.SH", "IF2509"]'::jsonb,
            '["ST001.SH"]'::jsonb,
            '[]'::jsonb
        )
        """
    )

    op.execute(
        """
        INSERT INTO strategies (
            strategy_id, name, description, enabled, parameters, supported_markets
        ) VALUES (
            'ma_cross',
            '双均线交叉',
            '快线上穿慢线买入，下穿卖出',
            true,
            '{"symbols": ["600000.SH"], "fast": 5, "slow": 20, "interval": "1m", "quantity": "100"}'::jsonb,
            '["stock", "futures"]'::jsonb
        )
        """
    )


def downgrade() -> None:
    op.drop_index("idx_risk_checks_signal", table_name="risk_checks")
    op.drop_index("idx_risk_checks_order", table_name="risk_checks")
    op.drop_index("idx_risk_checks_time", table_name="risk_checks")
    op.drop_table("risk_checks")
    op.drop_table("risk_configs")
    op.drop_index("idx_signals_symbol", table_name="strategy_signals")
    op.drop_index("idx_signals_strategy", table_name="strategy_signals")
    op.drop_table("strategy_signals")
    op.drop_index("idx_strategy_runs_strategy", table_name="strategy_runs")
    op.drop_table("strategy_runs")
    op.drop_table("strategies")
