"""phase1 core tables

Revision ID: 0002_phase1_core
Revises: 0001_init
Create Date: 2026-07-20

阶段 1：枚举、账户/标的/系统配置、系统状态、审计与系统事件。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_phase1_core"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# PostgreSQL 枚举类型
ENUM_DEFS = {
    "market_type": ("stock", "futures"),
    "order_side_type": ("buy", "sell"),
    "signal_action_type": ("open", "close", "reduce", "increase"),
    "price_type": ("limit", "market"),
    "order_status_type": (
        "pending_risk",
        "risk_rejected",
        "submitting",
        "submitted",
        "partially_filled",
        "filled",
        "cancelled",
        "failed",
        "unknown",
    ),
    "system_status_type": (
        "initializing",
        "ready",
        "trading",
        "paused",
        "circuit_breaker",
        "emergency_stopped",
        "degraded",
        "offline",
    ),
    "risk_result_type": ("passed", "rejected", "warning"),
    "severity_type": ("info", "warning", "error", "critical"),
    "strategy_run_status_type": ("running", "paused", "stopped", "failed", "pending_confirm"),
    "account_status_type": ("active", "disabled"),
}


def _create_enums() -> dict[str, postgresql.ENUM]:
    enums: dict[str, postgresql.ENUM] = {}
    for name, values in ENUM_DEFS.items():
        enum_type = postgresql.ENUM(*values, name=name, create_type=False)
        enum_type.create(op.get_bind(), checkfirst=True)
        enums[name] = enum_type
    return enums


def _drop_enums() -> None:
    for name in reversed(list(ENUM_DEFS.keys())):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)


def upgrade() -> None:
    enums = _create_enums()

    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_no", sa.String(64), nullable=False),
        sa.Column("account_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("market", enums["market_type"], nullable=False),
        sa.Column("broker_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("sdk_account_ref", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", enums["account_status_type"], nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint("market", "account_no", name="uk_accounts_market_no"),
    )
    op.execute("COMMENT ON TABLE accounts IS '交易账户'")

    op.create_table(
        "instruments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("market", enums["market_type"], nullable=False),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("exchange", sa.String(32), nullable=False, server_default=""),
        sa.Column("price_tick", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("lot_size", sa.Numeric(20, 8), nullable=False, server_default="1"),
        sa.Column("multiplier", sa.Numeric(20, 8), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint("market", "symbol", name="uk_instruments_market_symbol"),
    )
    op.execute("COMMENT ON TABLE instruments IS '股票/期货合约基础信息'")

    op.create_table(
        "system_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("config_key", sa.String(128), nullable=False),
        sa.Column("config_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("encrypted_value", sa.LargeBinary(), nullable=True),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("config_key", name="uk_system_configs_key"),
    )
    op.execute("COMMENT ON TABLE system_configs IS '系统配置，敏感字段加密存储'")

    op.create_table(
        "system_state",
        sa.Column("id", sa.SmallInteger(), primary_key=True, server_default="1"),
        sa.Column("status", enums["system_status_type"], nullable=False, server_default="initializing"),
        sa.Column("status_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("status_since", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("id = 1", name="chk_system_state_singleton"),
    )
    op.execute("INSERT INTO system_state (id) VALUES (1)")

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("module", sa.String(64), nullable=False),
        sa.Column("object_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("object_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("request_summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("correlation_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("operator", sa.String(64), nullable=False, server_default="local_user"),
    )
    op.create_index("idx_audit_time", "audit_logs", ["event_time"], postgresql_ops={"event_time": "DESC"})
    op.create_index(
        "idx_audit_module",
        "audit_logs",
        ["module", "event_time"],
        postgresql_ops={"event_time": "DESC"},
    )
    op.create_index("idx_audit_object", "audit_logs", ["object_type", "object_id"])
    op.execute("COMMENT ON TABLE audit_logs IS '审计日志，只追加不修改'")

    op.create_table(
        "system_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("severity", enums["severity_type"], nullable=False, server_default="info"),
        sa.Column("module", sa.String(64), nullable=False),
        sa.Column("event_code", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_events_time", "system_events", ["event_time"], postgresql_ops={"event_time": "DESC"})
    op.create_index("idx_events_severity", "system_events", ["severity", "resolved"])
    op.execute("COMMENT ON TABLE system_events IS '系统事件和异常'")


def downgrade() -> None:
    op.drop_index("idx_events_severity", table_name="system_events")
    op.drop_index("idx_events_time", table_name="system_events")
    op.drop_table("system_events")

    op.drop_index("idx_audit_object", table_name="audit_logs")
    op.drop_index("idx_audit_module", table_name="audit_logs")
    op.drop_index("idx_audit_time", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_table("system_state")
    op.drop_table("system_configs")
    op.drop_table("instruments")
    op.drop_table("accounts")

    _drop_enums()
