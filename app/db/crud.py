"""Database CRUD helpers."""

from __future__ import annotations
import io
import base64
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import pyotp
import qrcode
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import (
    MastodonApp, MastodonOAuthState, MiAuthSession,
    OAuthToken, RegisteredApp, User,
)


# ---------------------------------------------------------------------------
# パスワード / TOTP
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def generate_totp_secret() -> str:
    return pyotp.random_base32()

def get_totp_uri(secret: str, username: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=username, issuer_name=settings.APP_NAME
    )

def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)

def generate_totp_qr_base64(secret: str, username: str) -> str:
    """QRコードをBase64エンコードしたPNG文字列で返す。"""
    uri = get_totp_uri(secret, username)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()

async def create_user(
    db: AsyncSession, *, username: str, password: str,
    display_name: str | None = None,
) -> User:
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        display_name=display_name or username,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()
    return user

async def authenticate_user(
    db: AsyncSession, *, username: str, password: str,
) -> User | None:
    user = await get_user_by_username(db, username)
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user

async def enable_totp(db: AsyncSession, user_id: str, secret: str) -> None:
    await db.execute(
        update(User).where(User.id == user_id)
        .values(totp_secret=secret, totp_enabled=True)
    )

async def disable_totp(db: AsyncSession, user_id: str) -> None:
    await db.execute(
        update(User).where(User.id == user_id)
        .values(totp_secret=None, totp_enabled=False)
    )

async def set_mastodon_credentials(
    db: AsyncSession, user_id: str, *,
    token: str, instance: str, account_id: str,
) -> None:
    await db.execute(
        update(User).where(User.id == user_id)
        .values(
            mastodon_token=token,
            mastodon_instance=instance,
            mastodon_account_id=account_id,
        )
    )


# ---------------------------------------------------------------------------
# RegisteredApp
# ---------------------------------------------------------------------------

async def create_app(
    db: AsyncSession, *, name: str, website: str | None,
    redirect_uris: str, scopes: str = "read write follow push",
) -> RegisteredApp:
    app = RegisteredApp(
        id=str(uuid.uuid4()),
        name=name, website=website,
        redirect_uris=redirect_uris, scopes=scopes,
        client_id=f"proxy_{secrets.token_urlsafe(16)}",
        client_secret=secrets.token_urlsafe(32),
    )
    db.add(app)
    await db.flush()
    return app

async def get_app_by_client_id(db: AsyncSession, client_id: str) -> RegisteredApp | None:
    result = await db.execute(
        select(RegisteredApp).where(RegisteredApp.client_id == client_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# MiAuthSession
# ---------------------------------------------------------------------------

async def create_miauth_session(
    db: AsyncSession, *, session_id: str,
    app_id: str | None = None, redirect_uri: str | None = None,
    scopes: str = "read write follow push",
    app_name: str = "", permission: str = "",
) -> MiAuthSession:
    session = MiAuthSession(
        session_id=session_id, app_id=app_id,
        redirect_uri=redirect_uri, scopes=scopes,
        app_name=app_name, permission=permission,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.MIAUTH_SESSION_TTL),
    )
    db.add(session)
    await db.flush()
    return session

async def get_miauth_session(db: AsyncSession, session_id: str) -> MiAuthSession | None:
    result = await db.execute(
        select(MiAuthSession).where(
            MiAuthSession.session_id == session_id,
            MiAuthSession.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()

async def set_session_pending_2fa(
    db: AsyncSession, session_id: str, user_id: str,
) -> None:
    """パスワード認証済み・2FAはまだのセッション状態を記録する。"""
    await db.execute(
        update(MiAuthSession)
        .where(MiAuthSession.session_id == session_id)
        .values(pending_user_id=user_id)
    )

async def authorize_miauth_session(
    db: AsyncSession, *, session_id: str, user_id: str,
) -> MiAuthSession | None:
    await db.execute(
        update(MiAuthSession)
        .where(MiAuthSession.session_id == session_id)
        .values(user_id=user_id, authorized=True, pending_user_id=None)
    )
    await db.flush()
    return await get_miauth_session(db, session_id)

async def delete_expired_sessions(db: AsyncSession) -> int:
    result = await db.execute(
        delete(MiAuthSession).where(
            MiAuthSession.expires_at <= datetime.now(timezone.utc),
            MiAuthSession.authorized == False,  # noqa: E712
        )
    )
    return result.rowcount


# ---------------------------------------------------------------------------
# OAuthToken
# ---------------------------------------------------------------------------

async def create_oauth_token(
    db: AsyncSession, *, session_id: str | None,
    app_id: str | None, user_id: str,
    scopes: str = "read write follow push",
) -> OAuthToken:
    token = OAuthToken(
        access_token=secrets.token_urlsafe(40),
        session_id=session_id, app_id=app_id,
        user_id=user_id, scopes=scopes,
    )
    db.add(token)
    await db.flush()
    return token

async def get_token_by_access_token(db: AsyncSession, access_token: str) -> OAuthToken | None:
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.access_token == access_token,
            OAuthToken.revoked == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()

async def get_token_with_user(
    db: AsyncSession, access_token: str,
) -> tuple[OAuthToken, User] | None:
    result = await db.execute(
        select(OAuthToken, User)
        .join(User, OAuthToken.user_id == User.id)
        .where(
            OAuthToken.access_token == access_token,
            OAuthToken.revoked == False,  # noqa: E712
        )
    )
    row = result.first()
    return (row[0], row[1]) if row else None

async def touch_token(db: AsyncSession, access_token: str) -> None:
    await db.execute(
        update(OAuthToken).where(OAuthToken.access_token == access_token)
        .values(last_used_at=datetime.now(timezone.utc))
    )

async def revoke_token(db: AsyncSession, access_token: str) -> None:
    await db.execute(
        update(OAuthToken).where(OAuthToken.access_token == access_token)
        .values(revoked=True)
    )


# ---------------------------------------------------------------------------
# MastodonApp
# ---------------------------------------------------------------------------

async def get_or_create_mastodon_app(
    db: AsyncSession, *, instance_url: str,
    client_id: str, client_secret: str,
) -> MastodonApp:
    result = await db.execute(
        select(MastodonApp).where(MastodonApp.instance_url == instance_url)
    )
    app = result.scalar_one_or_none()
    if app:
        return app
    app = MastodonApp(
        id=str(uuid.uuid4()),
        instance_url=instance_url,
        client_id=client_id,
        client_secret=client_secret,
    )
    db.add(app)
    await db.flush()
    return app

async def get_mastodon_app(db: AsyncSession, instance_url: str) -> MastodonApp | None:
    result = await db.execute(
        select(MastodonApp).where(MastodonApp.instance_url == instance_url)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# MastodonOAuthState
# ---------------------------------------------------------------------------

async def create_mastodon_oauth_state(
    db: AsyncSession, *, user_id: str,
    miauth_session_id: str | None, mastodon_app_id: str,
    mastodon_instance: str,
) -> MastodonOAuthState:
    state = MastodonOAuthState(
        id=str(uuid.uuid4()),
        state=secrets.token_urlsafe(32),
        user_id=user_id,
        miauth_session_id=miauth_session_id,
        mastodon_app_id=mastodon_app_id,
        mastodon_instance=mastodon_instance,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.MASTODON_OAUTH_STATE_TTL),
    )
    db.add(state)
    await db.flush()
    return state

async def get_mastodon_oauth_state(db: AsyncSession, state: str) -> MastodonOAuthState | None:
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(MastodonOAuthState)
        .options(
            selectinload(MastodonOAuthState.mastodon_app),
            selectinload(MastodonOAuthState.user),
        )
        .where(
            MastodonOAuthState.state == state,
            MastodonOAuthState.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()

async def delete_mastodon_oauth_state(db: AsyncSession, state_id: str) -> None:
    await db.execute(
        delete(MastodonOAuthState).where(MastodonOAuthState.id == state_id)
    )
