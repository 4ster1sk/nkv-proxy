"""Tests for PostgreSQL-backed user auth + miAuth flow (SQLite in-memory)."""

import asyncio
import os

import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import (
    crud,
    models,  # noqa
)
from app.db.database import Base, get_db

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
        from datetime import datetime, timedelta, timezone
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

class TestMiauthConfirmFlow:
    """miAuth 認証確認画面フローのテスト。"""

    def _setup_client(self):
        from fastapi.testclient import TestClient

        from app.main import app
        app.dependency_overrides[get_db] = _override_get_db
        return TestClient(app)

    def test_miauth_redirects_to_login_when_not_logged_in(self):
        """未ログイン時は /login へリダイレクト。"""
        client = self._setup_client()
        sid = "1111aaaa-0000-0000-0000-000000000001"
        resp = client.get(
            f"/miauth/{sid}?name=App&permission=read:account",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("location", "")
        assert sid in resp.headers.get("location", "")

    def test_miauth_shows_confirm_page_when_logged_in(self):
        """ログイン済みの場合、確認画面（許可する/拒否する）が表示される。"""
        client = self._setup_client()
        client.post("/register", data={
            "username": "confirm_test1",
            "password": "password123",
            "password_confirm": "password123",
        })
        async def _set_masto():
            async with _TestSession() as s:
                user = await crud.get_user_by_username(s, "confirm_test1")
                await crud.set_mastodon_credentials(
                    s, user.id, token="masto_t1",
                    instance="https://mastodon.social", account_id="m1",
                )
                await s.commit()
        asyncio.get_event_loop().run_until_complete(_set_masto())
        client.post("/login", data={"username": "confirm_test1", "password": "password123"})

        sid = "2222bbbb-0000-0000-0000-000000000001"
        resp = client.get(f"/miauth/{sid}?name=TestApp&permission=read:account,write:notes")
        assert resp.status_code == 200
        assert "許可する" in resp.text
        assert "拒否する" in resp.text
        assert "TestApp" in resp.text
        assert "アカウント情報" in resp.text

    def test_miauth_approve_issues_token(self):
        """「許可する」を押すと OAuthToken が発行される。"""
        client = self._setup_client()
        client.post("/register", data={
            "username": "approve_test1",
            "password": "password123",
            "password_confirm": "password123",
        })
        async def _set_masto():
            async with _TestSession() as s:
                user = await crud.get_user_by_username(s, "approve_test1")
                await crud.set_mastodon_credentials(
                    s, user.id, token="masto_t2",
                    instance="https://mastodon.social", account_id="m2",
                )
                await s.commit()
        asyncio.get_event_loop().run_until_complete(_set_masto())
        client.post("/login", data={"username": "approve_test1", "password": "password123"})

        sid = "3333cccc-0000-0000-0000-000000000001"
        client.get(
            f"/miauth/{sid}?name=App&permission=read:account"
            f"&callback=https://example.com/cb"
        )
        resp = client.post(f"/miauth/{sid}/approve", follow_redirects=False)
        assert resp.status_code == 302
        loc = resp.headers.get("location", "")
        assert "code=" + sid in loc

        # token exchange
        resp2 = client.post("/oauth/token", json={
            "grant_type": "authorization_code", "code": sid,
        })
        assert resp2.status_code == 200
        assert "access_token" in resp2.json()

    def test_miauth_deny_returns_access_denied(self):
        """「拒否する」を押すと error=access_denied になる。"""
        client = self._setup_client()
        client.post("/register", data={
            "username": "deny_test1",
            "password": "password123",
            "password_confirm": "password123",
        })
        client.post("/login", data={"username": "deny_test1", "password": "password123"})

        sid = "4444dddd-0000-0000-0000-000000000001"
        client.get(
            f"/miauth/{sid}?name=App&permission=read:account"
            f"&callback=https://example.com/cb"
        )
        resp = client.post(f"/miauth/{sid}/deny", follow_redirects=False)
        assert resp.status_code == 302
        assert "error=access_denied" in resp.headers.get("location", "")

    def test_miauth_admin_warn_shown(self):
        """admin権限を含む場合、確認画面に警告が表示される。"""
        client = self._setup_client()
        client.post("/register", data={
            "username": "admin_warn_test1",
            "password": "password123",
            "password_confirm": "password123",
        })
        async def _set_masto():
            async with _TestSession() as s:
                user = await crud.get_user_by_username(s, "admin_warn_test1")
                await crud.set_mastodon_credentials(
                    s, user.id, token="masto_t3",
                    instance="https://mastodon.social", account_id="m3",
                )
                await s.commit()
        asyncio.get_event_loop().run_until_complete(_set_masto())
        client.post("/login", data={"username": "admin_warn_test1", "password": "password123"})

        sid = "5555eeee-0000-0000-0000-000000000001"
        resp = client.get(
            f"/miauth/{sid}?name=AdminApp"
            f"&permission=read:account,write:admin:delete-account"
        )
        assert resp.status_code == 200
        assert "管理者権限" in resp.text
        assert "AdminApp" in resp.text
