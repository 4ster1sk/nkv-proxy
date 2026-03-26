"""add limit_max_tl and limit_max_notifications to users

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("limit_max_tl", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("limit_max_notifications", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "limit_max_notifications")
    op.drop_column("users", "limit_max_tl")
