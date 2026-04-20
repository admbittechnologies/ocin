"""Add threads, messages tables and agent_memory expires_at

Revision ID: 001
Revises:
Create Date: 2026-04-02 13:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create threads table
    op.create_table(
        'threads',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('agent_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False, server_default='New Chat'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_message_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_threads_agent_id'), 'threads', ['agent_id'], unique=False)
    op.create_index(op.f('ix_threads_id'), 'threads', ['id'], unique=False)
    op.create_index(op.f('ix_threads_last_message_at'), 'threads', ['last_message_at'], unique=False)
    op.create_index(op.f('ix_threads_user_id'), 'threads', ['user_id'], unique=False)

    # Create messages table
    op.create_table(
        'messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('thread_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['thread_id'], ['threads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_messages_id'), 'messages', ['id'], unique=False)
    op.create_index(op.f('ix_messages_thread_id'), 'messages', ['thread_id'], unique=False)

    # Add expires_at column to agent_memory table
    op.add_column('agent_memory', sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_index(op.f('ix_agent_memory_expires'), 'agent_memory', ['expires_at'], unique=False)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index(op.f('ix_agent_memory_expires'), table_name='agent_memory')
    op.drop_index(op.f('ix_messages_thread_id'), table_name='messages')
    op.drop_index(op.f('ix_messages_id'), table_name='messages')
    op.drop_index(op.f('ix_threads_last_message_at'), table_name='threads')
    op.drop_index(op.f('ix_threads_user_id'), table_name='threads')
    op.drop_index(op.f('ix_threads_agent_id'), table_name='threads')
    op.drop_index(op.f('ix_threads_id'), table_name='threads')

    # Drop tables
    op.drop_table('messages')
    op.drop_table('threads')

    # Remove expires_at column from agent_memory
    op.drop_column('agent_memory', 'expires_at')
