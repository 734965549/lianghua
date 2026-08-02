"""strategy builder: rule DSL and versioning

Revision ID: 0011_strategy_builder
Revises: 0010_market_snapshot_identity
Create Date: 2026-08-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_strategy_builder"
down_revision: Union[str, None] = "0010_market_snapshot_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "strategies",
        sa.Column("kind", sa.String(16), nullable=False, server_default="builtin"),
    )
    op.add_column(
        "strategies",
        sa.Column("status", sa.String(16), nullable=False, server_default="published"),
    )
    op.add_column(
        "strategies",
        sa.Column("current_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "strategies",
        sa.Column("is_editable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "strategies",
        sa.Column(
            "definition_schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    op.execute(
        """
        UPDATE strategies
        SET kind = 'builtin', status = 'published', is_editable = false
        WHERE strategy_id IN ('ma_cross', 'grid_trading', 'multi_factor')
        """
    )

    op.create_table(
        "strategy_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("strategy_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "definition",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "parameters_schema",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("checksum", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("strategy_id", "version", name="uk_strategy_versions_id_ver"),
    )
    op.create_index(
        "idx_strategy_versions_strategy",
        "strategy_versions",
        ["strategy_id", "version"],
    )
    op.execute("COMMENT ON TABLE strategy_versions IS '策略规则版本（DSL 快照）'")


def downgrade() -> None:
    op.drop_index("idx_strategy_versions_strategy", table_name="strategy_versions")
    op.drop_table("strategy_versions")
    op.drop_column("strategies", "definition_schema_version")
    op.drop_column("strategies", "is_editable")
    op.drop_column("strategies", "current_version")
    op.drop_column("strategies", "status")
    op.drop_column("strategies", "kind")
