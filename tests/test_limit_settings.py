"""Tests for per-user limit clamping and /settings/limits page."""
import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from tests.conftest import TEST_ACCESS_TOKEN, TEST_USER_ID, _TestSession


def _auth(token: str = TEST_ACCESS_TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestLimitClamping:
    """limit パラメータが上限でクランプされ 422 にならないことを確認する。"""

    def test_notifications_limit_over_default_is_clamped(self, client: TestClient):
        """limit=50 を送っても 422 にならず Mastodon へは clamp 後の値が渡る。"""
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.get_notifications = AsyncMock(return_value=[])
            resp = client.get(
                "/api/v1/notifications?limit=50", headers=_auth()
            )
        assert resp.status_code == 200
        # Mastodon へ渡った limit がデフォルト上限(40)以下であること
        call_kwargs = mock_instance.get_notifications.call_args[1]
        assert call_kwargs["limit"] <= 40

    def test_home_timeline_limit_over_default_is_clamped(self, client: TestClient):
        """ホームTLで limit=100 を送っても 422 にならずクランプされる。"""
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.home_timeline = AsyncMock(return_value=[])
            resp = client.get(
                "/api/v1/timelines/home?limit=100", headers=_auth()
            )
        assert resp.status_code == 200
        call_kwargs = mock_instance.home_timeline.call_args[1]
        assert call_kwargs["limit"] <= 40

    def test_public_timeline_limit_over_default_is_clamped(self, client: TestClient):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.public_timeline = AsyncMock(return_value=[])
            resp = client.get(
                "/api/v1/timelines/public?limit=999", headers=_auth()
            )
        assert resp.status_code == 200
        call_kwargs = mock_instance.public_timeline.call_args[1]
        assert call_kwargs["limit"] <= 40


class TestUserLimitSettings:
    """ユーザーの limit 設定が反映されることを確認する。"""

    def _set_user_limits(self, tl: int | None, notif: int | None):
        """テスト用ユーザーの limit 設定を DB に直接書き込む。"""
        from sqlalchemy import update

        from app.db.models import User

        async def _update():
            async with _TestSession() as s:
                await s.execute(
                    update(User).where(User.id == TEST_USER_ID).values(
                        limit_max_tl=tl,
                        limit_max_notifications=notif,
                    )
                )
                await s.commit()

        asyncio.get_event_loop().run_until_complete(_update())

    def test_user_limit_tl_is_respected(self, client: TestClient):
        """ユーザーが limit_max_tl=20 に設定している場合、limit=50 → 20 にクランプされる。"""
        self._set_user_limits(tl=20, notif=None)
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.home_timeline = AsyncMock(return_value=[])
            resp = client.get(
                "/api/v1/timelines/home?limit=50", headers=_auth()
            )
        assert resp.status_code == 200
        call_kwargs = mock_instance.home_timeline.call_args[1]
        assert call_kwargs["limit"] == 20

    def test_user_limit_notifications_is_respected(self, client: TestClient):
        """ユーザーが limit_max_notifications=10 に設定している場合、limit=50 → 10 にクランプされる。"""
        self._set_user_limits(tl=None, notif=10)
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.get_notifications = AsyncMock(return_value=[])
            resp = client.get(
                "/api/v1/notifications?limit=50", headers=_auth()
            )
        assert resp.status_code == 200
        call_kwargs = mock_instance.get_notifications.call_args[1]
        assert call_kwargs["limit"] == 10

    def test_null_limit_falls_back_to_default(self, client: TestClient):
        """ユーザーの limit 設定が NULL の場合、グローバルデフォルト(40)にクランプされる。"""
        self._set_user_limits(tl=None, notif=None)
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.home_timeline = AsyncMock(return_value=[])
            resp = client.get(
                "/api/v1/timelines/home?limit=50", headers=_auth()
            )
        assert resp.status_code == 200
        call_kwargs = mock_instance.home_timeline.call_args[1]
        assert call_kwargs["limit"] == 40


class TestSettingsLimitsPage:
    """設定画面 /settings/limits の基本動作を確認する。"""

    def test_page_requires_login(self, client: TestClient):
        resp = client.get("/settings/limits", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/login" in resp.headers.get("location", "")

    def test_page_renders_for_authenticated_user(self, client: TestClient):
        # Cookie でセッション認証
        client.cookies.set("proxy_session", TEST_ACCESS_TOKEN)
        resp = client.get("/settings/limits")
        assert resp.status_code == 200
        assert "limit" in resp.text
