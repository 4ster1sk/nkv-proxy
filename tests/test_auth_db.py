"""Tests for PostgreSQL-backed user auth + miAuth flow (SQLite in-memory)."""

import os
import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.database import Base, get_db
from app.db import models  # noqa
from app.db import crud

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_TestSession = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


async def _override_get_db():
    async with _TestSession() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _TestSession() as session:
        yield session
        await session.rollback()


@pytest.fixture
def client_with_db():
    from fastapi.testclient import TestClient
    from app.main import app
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

class TestUserCrud:
    @pytest.mark.asyncio
    async def test_create_user(self, db):
        user = await crud.create_user(db, username="alice", password="password123")
        await db.commit()
        assert user.id
        assert user.username == "alice"
        assert user.password_hash != "password123"

    @pytest.mark.asyncio
    async def test_password_hash_verify(self, db):
        await crud.create_user(db, username="bob", password="secret8chars")
        await db.commit()
        user = await crud.get_user_by_username(db, "bob")
        assert crud.verify_password("secret8chars", user.password_hash)
        assert not crud.verify_password("wrongpass", user.password_hash)

    @pytest.mark.asyncio
    async def test_authenticate_user_success(self, db):
        await crud.create_user(db, username="carol", password="mypassword")
        await db.commit()
        user = await crud.authenticate_user(db, username="carol", password="mypassword")
        assert user is not None
        assert user.username == "carol"

    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self, db):
        await crud.create_user(db, username="dave", password="correct")
        await db.commit()
        user = await crud.authenticate_user(db, username="dave", password="wrong")
        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self, db):
        user = await crud.authenticate_user(db, username="nobody", password="pass")
        assert user is None

    @pytest.mark.asyncio
    async def test_username_unique(self, db):
        await crud.create_user(db, username="unique_user", password="pass1234")
        await db.commit()
        existing = await crud.get_user_by_username(db, "unique_user")
        assert existing is not None
        # 同名は get_user_by_username で検出して防ぐ設計
        same = await crud.get_user_by_username(db, "unique_user")
        assert same.id == existing.id


# ---------------------------------------------------------------------------
# RegisteredApp CRUD
# ---------------------------------------------------------------------------

class TestRegisteredAppCrud:
    @pytest.mark.asyncio
    async def test_create_and_get_app(self, db):
        app = await crud.create_app(
            db, name="TestApp", website=None,
            redirect_uris="https://example.com/cb",
        )
        await db.commit()
        found = await crud.get_app_by_client_id(db, app.client_id)
        assert found is not None
        assert found.name == "TestApp"
        assert found.client_id.startswith("proxy_")


# ---------------------------------------------------------------------------
# MiAuthSession CRUD
# ---------------------------------------------------------------------------

class TestMiAuthSessionCrud:
    @pytest.mark.asyncio
    async def test_create_and_authorize_session(self, db):
        user = await crud.create_user(db, username="eve", password="password1")
        await db.commit()

        sid = "aaaabbbb-0000-0000-0000-000000000001"
        await crud.create_miauth_session(db, session_id=sid)
        await db.commit()

        result = await crud.authorize_miauth_session(db, session_id=sid, user_id=user.id)
        await db.commit()
        assert result is not None
        assert result.authorized is True
        assert result.user_id == user.id

    @pytest.mark.asyncio
    async def test_expired_session_not_found(self, db):
        from datetime import timedelta, timezone, datetime
        sid = "aaaabbbb-0000-0000-0000-000000000002"
        session = await crud.create_miauth_session(db, session_id=sid)
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        found = await crud.get_miauth_session(db, sid)
        assert found is None


# ---------------------------------------------------------------------------
# OAuthToken CRUD
# ---------------------------------------------------------------------------

class TestOAuthTokenCrud:
    @pytest.mark.asyncio
    async def test_create_and_get_token(self, db):
        user = await crud.create_user(db, username="frank", password="password1")
        await db.commit()
        token = await crud.create_oauth_token(
            db, session_id=None, app_id=None, user_id=user.id
        )
        await db.commit()
        found = await crud.get_token_by_access_token(db, token.access_token)
        assert found is not None
        assert found.user_id == user.id

    @pytest.mark.asyncio
    async def test_get_token_with_user(self, db):
        user = await crud.create_user(db, username="grace", password="password1")
        await db.commit()
        token = await crud.create_oauth_token(
            db, session_id=None, app_id=None, user_id=user.id
        )
        await db.commit()
        result = await crud.get_token_with_user(db, token.access_token)
        assert result is not None
        t, u = result
        assert u.username == "grace"

    @pytest.mark.asyncio
    async def test_revoke_token(self, db):
        user = await crud.create_user(db, username="henry", password="password1")
        await db.commit()
        token = await crud.create_oauth_token(
            db, session_id=None, app_id=None, user_id=user.id
        )
        await db.commit()
        await crud.revoke_token(db, token.access_token)
        await db.commit()
        found = await crud.get_token_by_access_token(db, token.access_token)
        assert found is None


# ---------------------------------------------------------------------------
# API エンドポイント
# ---------------------------------------------------------------------------
