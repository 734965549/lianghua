"""set_updated_at triggers for tables with updated_at

Revision ID: 0007_updated_at_triggers
Revises: 0006_ai_reports
Create Date: 2026-07-20

对应 database-design.md 迁移 8：原生 SQL UPDATE 也会刷新 updated_at。
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007_updated_at_triggers"
down_revision: Union[str, None] = "0006_ai_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "accounts",
    "instruments",
    "system_configs",
    "system_state",
    "strategies",
    "strategy_runs",
    "risk_configs",
    "orders",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS trigger AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in _TABLES:
        op.execute(
            f"""
            DROP TRIGGER IF EXISTS trg_{table}_updated ON {table};
            CREATE TRIGGER trg_{table}_updated
              BEFORE UPDATE ON {table}
              FOR EACH ROW EXECUTE FUNCTION set_updated_at();
            """
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated ON {table};")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
