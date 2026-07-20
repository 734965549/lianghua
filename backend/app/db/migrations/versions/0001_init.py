"""init empty schema baseline

Revision ID: 0001_init
Revises:
Create Date: 2026-07-20

阶段 0 空迁移基线，后续阶段按表追加迁移。
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
