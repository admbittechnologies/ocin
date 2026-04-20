"""add kind column to messages table

Revision ID: acf6d4944d1f
Revises: 005
Create Date: 2026-04-13 07:02:00.887641

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'acf6d4944d1f'
down_revision: Union[str, Sequence[str], None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('messages', sa.Column('kind', sa.String(20), nullable=False, server_default='normal'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('messages', 'kind')
