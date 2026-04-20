"""Add indexes for message and thread cleanup queries.

Revision ID: 002
Revises: 001_add_threads_messages_and_memory_expiry
Create Date: 2026-04-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add index on messages.created_at for efficient cleanup queries
    op.create_index(
        'idx_messages_created_at',
        'messages',
        ['created_at'],
    )

    # Add index on threads.created_at for cleanup queries
    op.create_index(
        'idx_threads_created_at',
        'threads',
        ['created_at'],
    )

    # Add index on threads.last_message_at for cleanup queries (already exists but ensure it's there)
    op.create_index(
        'idx_threads_last_message_at',
        'threads',
        ['last_message_at'],
        if_not_exists=True,
    )


def downgrade() -> None:
    # Remove indexes
    op.drop_index('idx_messages_created_at', table_name='messages')
    op.drop_index('idx_threads_created_at', table_name='threads')
    op.drop_index('idx_threads_last_message_at', table_name='threads')
