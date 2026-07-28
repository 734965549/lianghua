"""audit_logs append-only at database layer

Revision ID: 0008_audit_append_only
Revises: 0007_updated_at_triggers
Create Date: 2026-07-20

禁止 UPDATE/DELETE audit_logs，保证「只追加不修改」在 DB 层生效。
TRUNCATE 不受本触发器影响（测试清理仍可用）。
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008_audit_append_only"
down_revision: Union[str, None] = "0007_updated_at_triggers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_audit_logs_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit_logs is append-only: % not allowed', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_audit_logs_no_update ON audit_logs;
        CREATE TRIGGER trg_audit_logs_no_update
          BEFORE UPDATE ON audit_logs
          FOR EACH ROW EXECUTE FUNCTION forbid_audit_logs_mutation();
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_audit_logs_no_delete ON audit_logs;
        CREATE TRIGGER trg_audit_logs_no_delete
          BEFORE DELETE ON audit_logs
          FOR EACH ROW EXECUTE FUNCTION forbid_audit_logs_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_update ON audit_logs;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_delete ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS forbid_audit_logs_mutation();")
