"""Add attachments column to messages table

Revision ID: 005
Revises:
Create Date: 2026-04-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add attachments JSONB column to messages table
    op.add_column('messages', sa.Column('attachments', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Remove attachments column from messages table
    op.drop_column('messages', 'attachments')