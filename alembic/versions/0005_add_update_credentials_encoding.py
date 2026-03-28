"""add update_credentials_encoding to mastodon_apps

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mastodon_apps",
        sa.Column(
            "update_credentials_encoding",
            sa.String(32),
            nullable=False,
            server_default="form-urlencoded",
        ),
    )


def downgrade() -> None:
    op.drop_column("mastodon_apps", "update_credentials_encoding")
