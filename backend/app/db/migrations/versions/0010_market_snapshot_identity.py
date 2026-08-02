"""Make market snapshot writes idempotent.

Revision ID: 0010_market_snapshot_identity
Revises: cd43d49db9d3
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0010_market_snapshot_identity"
down_revision: Union[str, None] = "cd43d49db9d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BACKUP_TABLE = "market_snapshot_duplicates_backup_0010"
_COLUMNS = (
    "id, symbol, market, quote_time, last_price, change_rate, volume, "
    "bid_price, ask_price, bid_volume, ask_volume, raw_payload, created_at"
)


def upgrade() -> None:
    # Prevent a writer from inserting another duplicate between cleanup and
    # constraint creation. Readers can continue while the migration runs.
    op.execute("LOCK TABLE market_snapshots IN SHARE ROW EXCLUSIVE MODE")
    op.execute(
        f"""
        CREATE TABLE {_BACKUP_TABLE}
        (LIKE market_snapshots INCLUDING DEFAULTS INCLUDING GENERATED)
        """
    )
    op.execute(
        f"""
        INSERT INTO {_BACKUP_TABLE} ({_COLUMNS})
        SELECT {_COLUMNS}
        FROM (
            SELECT
                market_snapshots.*,
                row_number() OVER (
                    PARTITION BY market, symbol, quote_time
                    ORDER BY created_at DESC, id DESC
                ) AS duplicate_rank
            FROM market_snapshots
        ) AS ranked
        WHERE duplicate_rank > 1
        """
    )
    op.execute(
        f"""
        DELETE FROM market_snapshots AS snapshots
        USING {_BACKUP_TABLE} AS duplicates
        WHERE snapshots.id = duplicates.id
        """
    )
    op.create_unique_constraint(
        "uq_market_snapshots_identity",
        "market_snapshots",
        ["market", "symbol", "quote_time"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_market_snapshots_identity",
        "market_snapshots",
        type_="unique",
    )
    op.execute(
        f"""
        INSERT INTO market_snapshots ({_COLUMNS})
        SELECT {_COLUMNS}
        FROM {_BACKUP_TABLE}
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.drop_table(_BACKUP_TABLE)
