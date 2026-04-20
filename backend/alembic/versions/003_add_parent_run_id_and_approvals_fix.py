"""Add parent_run_id column to runs and fix approvals table.

Revision ID: 003
Revises: 002_add_message_indexes

Creates:
- parent_run_id column on runs table with FK to runs.id
- approvals table with resolved_at column, proper FK constraints, and indexes
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add parent_run_id column to runs table (if not already exists)
    op.add_column(
        'runs',
        sa.Column(
            'parent_run_id',
            postgresql.UUID(),
            nullable=True,
            comment='Parent run that requested approval'
        )
    )

    # Create foreign key for parent_run_id
    try:
        op.create_foreign_key(
            'fk_runs_parent_run_id_runs',
            'runs',
            'runs',
            ['parent_run_id'],
            ['id'],
            ondelete='SET NULL'
        )
    except Exception:
        # FK might already exist if column was added previously
        pass

    # Create index on parent_run_id for better performance
    op.create_index(
        'idx_runs_parent_run_id',
        'runs',
        ['parent_run_id']
    )

    # Create approvals table
    op.create_table(
        'approvals',
        sa.Column('id', postgresql.UUID(), nullable=False, comment='Unique approval identifier'),
        sa.Column('user_id', postgresql.UUID(), nullable=False, comment='User who owns this approval'),
        sa.Column('agent_id', postgresql.UUID(), nullable=True, comment='Agent that requested approval'),
        sa.Column('run_id', postgresql.UUID(), nullable=True, comment='Run that created this approval'),
        sa.Column('schedule_id', postgresql.UUID(), nullable=True, comment='Schedule trigger (if applicable)'),
        sa.Column('kind', sa.String(64), nullable=False, comment='Type of approval requested'),
        sa.Column('title', sa.String(255), nullable=False, comment='Short user-facing summary'),
        sa.Column('description', sa.Text(), nullable=True, comment='Longer explanation'),
        sa.Column('payload', postgresql.JSONB(), nullable=True, server_default='{}', comment='Full payload the agent wants to execute'),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending', comment='pending | approved | rejected | expired'),
        sa.Column('resolved_at', sa.TIMESTAMP(timezone=True), nullable=True, comment='When user approved or rejected'),
        sa.Column('resolution_note', sa.Text(), nullable=True, comment='Optional note from user when approving/rejecting'),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=True, comment='Optional TTL for automatic expiry'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False, comment='When approval was created'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['schedule_id'], ['schedules.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for fast queries
    op.create_index(
        'idx_approvals_user_id_status',
        'approvals',
        ['user_id', 'status']
    )

    op.create_index(
        'idx_approvals_user_id_status_agent_id',
        'approvals',
        ['user_id', 'status', 'agent_id']
    )

    op.create_index(
        'idx_approvals_user_id_run_id',
        'approvals',
        ['user_id', 'run_id']
    )

    op.create_index(
        'idx_approvals_user_id_schedule_id',
        'approvals',
        ['user_id', 'schedule_id']
    )


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_approvals_user_id_schedule_id', table_name='approvals')
    op.drop_index('idx_approvals_user_id_run_id', table_name='approvals')
    op.drop_index('idx_approvals_user_id_status_agent_id', table_name='approvals')
    op.drop_index('idx_approvals_user_id_status', table_name='approvals')

    # Drop approvals table
    op.drop_table('approvals')

    # Drop parent_run_id index and FK
    op.drop_index('idx_runs_parent_run_id', table_name='runs')
    try:
        op.drop_constraint('fk_runs_parent_run_id_runs', 'runs', type_='foreignkey')
    except Exception:
        pass

    # Drop parent_run_id column
    op.drop_column('runs', 'parent_run_id')
