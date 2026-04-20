"""add resolved_at to approvals

Revision ID: 8d193d9060c2
Revises: 003
Create Date: 2026-04-08 06:55:48.106091

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d193d9060c2'
down_revision: Union[str, Sequence[str], None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'approvals',
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('approvals', 'resolved_at')
