"""add email verification columns

Revision ID: 008_add_email_verification
Revises: 8d193d9060c2
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = "008_add_email_verification"
down_revision = "007_add_source_to_agent_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("verification_token", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "verification_token")
    op.drop_column("users", "email_verified")
