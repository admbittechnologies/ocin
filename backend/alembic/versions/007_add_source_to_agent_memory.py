"""Add source column to agent_memory

Revision ID: 007_add_source_to_agent_memory
Revises: 006_add_user_memory_table
Create Date: 2026-04-16 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent_memory', sa.Column('source', sa.String(10), nullable=False, server_default='agent'))


def downgrade():
    op.drop_column('agent_memory', 'source')
