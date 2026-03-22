"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("mastodon_token", sa.Text, nullable=True),
        sa.Column("mastodon_instance", sa.Text, nullable=True),
        sa.Column("mastodon_account_id", sa.String(255), nullable=True),
        sa.Column("totp_secret", sa.Text, nullable=True),
        sa.Column("totp_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("bio", sa.Text, nullable=False, server_default=""),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("header_url", sa.Text, nullable=True),
        sa.Column("is_locked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_bot", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "registered_apps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("website", sa.Text, nullable=True),
        sa.Column("redirect_uris", sa.Text, nullable=False),
        sa.Column("scopes", sa.Text, nullable=False, server_default="read write follow push"),
        sa.Column("client_id", sa.String(255), nullable=False, unique=True),
        sa.Column("client_secret", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_table(
        "miauth_sessions",
        sa.Column("session_id", sa.String(36), primary_key=True),
        sa.Column("app_id", sa.String(36),
                  sa.ForeignKey("registered_apps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pending_user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("redirect_uri", sa.Text, nullable=True),
        sa.Column("scopes", sa.Text, nullable=False, server_default="read write follow push"),
        sa.Column("app_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("permission", sa.Text, nullable=False, server_default=""),
        sa.Column("authorized", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_miauth_sessions_expires_at", "miauth_sessions", ["expires_at"])

    op.create_table(
        "oauth_tokens",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("access_token", sa.Text, nullable=False, unique=True),
        sa.Column("session_id", sa.String(36),
                  sa.ForeignKey("miauth_sessions.session_id", ondelete="SET NULL"), nullable=True),
        sa.Column("app_id", sa.String(36),
                  sa.ForeignKey("registered_apps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scopes", sa.Text, nullable=False, server_default="read write follow push"),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_oauth_tokens_access_token", "oauth_tokens", ["access_token"])
    op.create_index("ix_oauth_tokens_user_id", "oauth_tokens", ["user_id"])

    op.create_table(
        "mastodon_apps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instance_url", sa.Text, nullable=False, unique=True),
        sa.Column("client_id", sa.Text, nullable=False),
        sa.Column("client_secret", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_table(
        "mastodon_oauth_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("state", sa.String(255), nullable=False, unique=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("miauth_session_id", sa.String(36),
                  sa.ForeignKey("miauth_sessions.session_id", ondelete="SET NULL"), nullable=True),
        sa.Column("mastodon_app_id", sa.String(36),
                  sa.ForeignKey("mastodon_apps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mastodon_instance", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_mastodon_oauth_states_state", "mastodon_oauth_states", ["state"])
    op.create_index("ix_mastodon_oauth_states_expires_at", "mastodon_oauth_states", ["expires_at"])


def downgrade() -> None:
    op.drop_table("mastodon_oauth_states")
    op.drop_table("mastodon_apps")
    op.drop_table("oauth_tokens")
    op.drop_table("miauth_sessions")
    op.drop_table("registered_apps")
    op.drop_table("users")

# NOTE: 0002 マイグレーションで追加されたカラム・テーブルは
# create_tables() (SQLAlchemy metadata.create_all) で自動作成される。
# alembic upgrade で適用する場合は 0002_add_admin_restriction.py を使用すること。
