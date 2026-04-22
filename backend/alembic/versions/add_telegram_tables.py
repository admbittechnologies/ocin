"""Add telegram_users and telegram_threads tables

Revision ID: add_telegram_tables
Revises: acf6d4944d1f
Create Date: 2026-04-22 17:32:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_telegram_tables'
down_revision = 'acf6d4944d1f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'telegram_users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('telegram_user_id', sa.String(64), nullable=False, index=True, unique=True),
        sa.Column('ocin_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('selected_agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'telegram_threads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('telegram_user_id', sa.String(64), nullable=False, index=True),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('thread_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('threads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('telegram_user_id', 'agent_id', name='uq_telegram_user_agent'),
    )


def downgrade():
    op.drop_table('telegram_threads')
    op.drop_table('telegram_users')
