"""
SQLAlchemy ORM モデル。

テーブル:
  users                  - このプロキシのローカルユーザー
  registered_apps        - Misskeyクライアントのアプリ登録
  miauth_sessions        - miAuth認可フロー一時セッション
  oauth_tokens           - 発行済みアクセストークン
  mastodon_apps          - 上流MastodonインスタンスのOAuthアプリ登録キャッシュ
  mastodon_oauth_states  - Mastodon OAuth フロー CSRF防止用一時状態
"""

from __future__ import annotations
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)

def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    # 上流 Mastodon への接続情報（Mastodon OAuth 完了後に設定）
    mastodon_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    mastodon_instance: Mapped[str | None] = mapped_column(Text, nullable=True)
    mastodon_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 2段階認証 (TOTP)
    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # プロフィール
    bio: Mapped[str] = mapped_column(Text, nullable=False, default="")
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    header_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    tokens: Mapped[list["OAuthToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    mastodon_states: Mapped[list["MastodonOAuthState"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# registered_apps  （Misskeyクライアントのアプリ登録）
# ---------------------------------------------------------------------------

class RegisteredApp(Base):
    __tablename__ = "registered_apps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_uris: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(
        Text, nullable=False, default="read write follow push"
    )
    client_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    client_secret: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    sessions: Mapped[list["MiAuthSession"]] = relationship(
        back_populates="app", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# miauth_sessions
# ---------------------------------------------------------------------------

class MiAuthSession(Base):
    __tablename__ = "miauth_sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    app_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("registered_apps.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    redirect_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[str] = mapped_column(
        Text, nullable=False, default="read write follow push"
    )
    app_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    permission: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 2FA pending: パスワード認証済みだが2FAがまだの状態
    pending_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    app: Mapped["RegisteredApp | None"] = relationship(back_populates="sessions")
    token: Mapped["OAuthToken | None"] = relationship(
        back_populates="session", uselist=False
    )


# ---------------------------------------------------------------------------
# oauth_tokens
# ---------------------------------------------------------------------------

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("miauth_sessions.session_id", ondelete="SET NULL"),
        nullable=True,
    )
    app_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("registered_apps.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    scopes: Mapped[str] = mapped_column(
        Text, nullable=False, default="read write follow push"
    )
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    session: Mapped["MiAuthSession | None"] = relationship(back_populates="token")
    user: Mapped["User"] = relationship(back_populates="tokens")

    __table_args__ = (
        UniqueConstraint("access_token", name="uq_oauth_tokens_access_token"),
    )


# ---------------------------------------------------------------------------
# mastodon_apps  （上流MastodonインスタンスのOAuthアプリ登録キャッシュ）
# ---------------------------------------------------------------------------

class MastodonApp(Base):
    __tablename__ = "mastodon_apps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    instance_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    client_secret: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    states: Mapped[list["MastodonOAuthState"]] = relationship(
        back_populates="mastodon_app", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# mastodon_oauth_states  （Mastodon OAuth CSRF防止用一時状態）
# ---------------------------------------------------------------------------

class MastodonOAuthState(Base):
    __tablename__ = "mastodon_oauth_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    state: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    miauth_session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("miauth_sessions.session_id", ondelete="SET NULL"),
        nullable=True,
    )
    mastodon_app_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mastodon_apps.id", ondelete="CASCADE"),
        nullable=False,
    )
    mastodon_instance: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    user: Mapped["User"] = relationship(back_populates="mastodon_states")
    mastodon_app: Mapped["MastodonApp"] = relationship(back_populates="states")
