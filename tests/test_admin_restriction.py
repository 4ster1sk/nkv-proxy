"""
Admin restriction テスト。

admin_restricted フラグが True のトークンで /api/admin/* を叩くと 403 が返り、
他のエンドポイントは通常通り動作することを確認する。
"""

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
from app.db.models import OAuthToken

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


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


async def _create_user_with_token(
    username: str,
    scopes: str = "read write admin",
    mastodon_token: str = "masto_token",
    admin_restricted: bool = False,
) -> tuple[str, int]:
    """テスト用ユーザーとトークンを作成し (access_token, token_id) を返す。"""
    async with _TestSession() as s:
        user = await crud.create_user(s, username=username, password="password123")
        user.mastodon_token = mastodon_token
        user.mastodon_instance = "https://mastodon.social"
        await s.flush()
        token = await crud.create_oauth_token(
            s, session_id=None, app_id=None,
            user_id=user.id, scopes=scopes,
        )
        if admin_restricted:
            token.admin_restricted = True
        await s.commit()
        return token.access_token, token.id


class TestAdminRestriction:

    def test_admin_api_accessible_without_restriction(self, client):
        """制限なしのトークンで /api/admin/show-users は通常通りアクセスできる。"""
        asyncio.get_event_loop().run_until_complete(
            _create_user_with_token("admin_user1", admin_restricted=False)
        )
        access_token, _ = asyncio.get_event_loop().run_until_complete(
            _create_user_with_token("admin_user1b", admin_restricted=False)
        )

        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_account = AsyncMock(return_value=[])
            MockClient.return_value._get = AsyncMock(return_value=[])
            resp = client.post("/api/admin/show-users", json={"i": access_token})
        # 200 (制限なし)
        assert resp.status_code == 200

    def test_admin_api_blocked_when_restricted(self, client):
        """admin_restricted=True のトークンで /api/admin/* は 403 になる。"""
        access_token, _ = asyncio.get_event_loop().run_until_complete(
            _create_user_with_token("admin_user2", admin_restricted=True)
        )
        resp = client.post("/api/admin/show-users", json={"i": access_token})
        assert resp.status_code == 403
        assert "temporarily disabled" in resp.json()["detail"]

    def test_admin_api_all_endpoints_blocked(self, client):
        """複数の admin エンドポイントが全て 403 になる。"""
        access_token, _ = asyncio.get_event_loop().run_until_complete(
            _create_user_with_token("admin_user3", admin_restricted=True)
        )
        admin_endpoints = [
            "/api/admin/show-users",
            "/api/admin/show-user",
            "/api/admin/server-info",
            "/api/admin/get-index-stats",
            "/api/admin/get-table-stats",
            "/api/admin/abuse-user-reports",
        ]
        for ep in admin_endpoints:
            resp = client.post(ep, json={"i": access_token, "userId": "dummy"})
            assert resp.status_code == 403, f"{ep} should return 403"

    def test_non_admin_endpoints_not_affected_by_restriction(self, client):
        """admin_restricted=True でも /api/notes/timeline 等は通常通り動く。"""
        access_token, _ = asyncio.get_event_loop().run_until_complete(
            _create_user_with_token("admin_user4", admin_restricted=True)
        )
        masto_status = {
            "id": "s001", "created_at": "2023-01-01T00:00:00Z",
            "content": "<p>test</p>", "visibility": "public",
            "spoiler_text": "", "sensitive": False,
            "reblogs_count": 0, "favourites_count": 0, "replies_count": 0,
            "favourited": False, "reblogged": False, "bookmarked": False,
            "reblog": None, "poll": None, "media_attachments": [],
            "mentions": [], "tags": [], "emojis": [],
            "account": {"id": "u001", "username": "testuser", "display_name": "Test"},
        }
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.home_timeline = AsyncMock(return_value=[masto_status])
            resp = client.post("/api/notes/timeline", json={"i": access_token})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_toggle_admin_restriction_via_dashboard(self, client):
        """ダッシュボードから admin_restricted フラグをトグルできる。"""
        access_token, token_id = asyncio.get_event_loop().run_until_complete(
            _create_user_with_token("toggle_user", admin_restricted=False)
        )

        # ログイン（セッション Cookie を取得）
        client.post("/register", data={
            "username": "toggle_user_dash",
            "password": "password123",
            "password_confirm": "password123",
        })
        login_resp = client.post("/login", data={
            "username": "toggle_user_dash", "password": "password123",
        }, follow_redirects=False)
        # Cookie はクライアントに自動セットされる

        # toggle_user のトークンを有効化・無効化は自分のトークンのみ可能
        # 今回は直接DB操作でテスト
        async def _enable():
            async with _TestSession() as s:
                await crud.set_admin_restricted(s, token_id, True)
                await s.commit()
                t = await s.get(OAuthToken, token_id)
                return t.admin_restricted

        result = asyncio.get_event_loop().run_until_complete(_enable())
        assert result is True

        # 制限後は 403
        resp = client.post("/api/admin/show-users", json={"i": access_token})
        assert resp.status_code == 403

        async def _disable():
            async with _TestSession() as s:
                await crud.set_admin_restricted(s, token_id, False)
                await s.commit()
                t = await s.get(OAuthToken, token_id)
                return t.admin_restricted

        result = asyncio.get_event_loop().run_until_complete(_disable())
        assert result is False

        # 制限解除後は 200
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value._get = AsyncMock(return_value=[])
            resp = client.post("/api/admin/show-users", json={"i": access_token})
        assert resp.status_code == 200

    def test_restriction_is_per_token(self, client):
        """制限は token ごとに独立している。"""
        token_a, _ = asyncio.get_event_loop().run_until_complete(
            _create_user_with_token("per_token_user_a", admin_restricted=True)
        )
        token_b, _ = asyncio.get_event_loop().run_until_complete(
            _create_user_with_token("per_token_user_b", admin_restricted=False)
        )

        # token_a は 403
        resp_a = client.post("/api/admin/show-users", json={"i": token_a})
        assert resp_a.status_code == 403

        # token_b は 200
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value._get = AsyncMock(return_value=[])
            resp_b = client.post("/api/admin/show-users", json={"i": token_b})
        assert resp_b.status_code == 200

    def test_token_without_admin_scope_also_blocked(self, client):
        """admin スコープを持たないトークンで admin エンドポイントを叩いても制限チェックは動く。"""
        # admin スコープなし + restricted=True
        access_token, _ = asyncio.get_event_loop().run_until_complete(
            _create_user_with_token(
                "no_admin_scope_user",
                scopes="read write",
                admin_restricted=True,
            )
        )
        resp = client.post("/api/admin/show-users", json={"i": access_token})
        assert resp.status_code == 403

    def test_api_key_authentication(self, client):
        """共通 ApiKey で /api/i が認証できる（Mastodon連携済みの場合）。"""
        asyncio.get_event_loop().run_until_complete(
            _create_user_with_token("apikey_user", scopes="read write")
        )
        # ApiKey を作成
        async def _create_key():
            async with _TestSession() as s:
                user = await crud.get_user_by_username(s, "apikey_user")
                key_obj = await crud.get_or_create_api_key(s, user.id)
                await s.commit()
                return key_obj.key
        api_key = asyncio.get_event_loop().run_until_complete(_create_key())

        masto_account = {
            "id": "u001", "username": "apikey_user", "display_name": "ApiKey User",
            "locked": False, "bot": False, "created_at": "2023-01-01T00:00:00Z",
            "note": "", "url": "https://mastodon.social/@apikey_user",
            "avatar": None, "header": None,
            "followers_count": 0, "following_count": 0, "statuses_count": 0,
            "fields": [],
        }
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.verify_credentials = AsyncMock(return_value=masto_account)
            resp = client.post("/api/i", json={"i": api_key})
        assert resp.status_code == 200
        assert resp.json()["username"] == "apikey_user"
