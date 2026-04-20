"""Rename avatar_color column to avatar and change type to VARCHAR(64).

Revision ID: 004
Revises: 8d193d9060c2
Create Date: 2026-04-10

Changes:
- Rename avatar_color column to avatar on agents table
- Change type from VARCHAR(7) to VARCHAR(64) to support avatar slugs like "avatar-07"
- Update all existing records to use default avatar slug "avatar-01"
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '8d193d9060c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename avatar_color to avatar and change type from VARCHAR(7) to VARCHAR(64)
    op.alter_column(
        "agents",
        "avatar_color",
        new_column_name="avatar",
        type_=sa.String(64),
        existing_type=sa.String(7),
        existing_nullable=False,
    )

    # Update all existing records to use default avatar slug
    # (since old hex color values are no longer meaningful)
    op.execute("UPDATE agents SET avatar = 'avatar-01'")


def downgrade() -> None:
    # Revert all records back to default hex color
    op.execute("UPDATE agents SET avatar_color = '#6366f1'")

    # Rename avatar back to avatar_color and change type back to VARCHAR(7)
    op.alter_column(
        "agents",
        "avatar",
        new_column_name="avatar_color",
        type_=sa.String(7),
        existing_type=sa.String(64),
        existing_nullable=False,
    )
