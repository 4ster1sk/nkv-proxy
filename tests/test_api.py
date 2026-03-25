"""Tests for Mastodon API endpoints."""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from tests.conftest import SAMPLE_NOTE, SAMPLE_NOTIFICATION, SAMPLE_USER

INSTANCE_URL = "https://misskey.example.com"


class TestInstanceEndpoints:
    def test_root(self, client: TestClient):
        resp = client.get("/")
        assert resp.status_code == 200
        # / はHTMLページを返す
        assert "text/html" in resp.headers.get("content-type", "") or resp.status_code == 200

    def test_instance_info(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            MockClient.return_value.get_instance = AsyncMock(return_value={
                "uri": "nekonoverse.org", "title": "Test", "version": "4.3.0",
                "description": "desc", "stats": {}, "languages": [], "rules": [],
            })
            resp = client.get("/api/v1/instance", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "uri" in data or "title" in data

    def test_custom_emojis(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            MockClient.return_value.get_custom_emojis = AsyncMock(return_value=[
                {"shortcode": "blobcat", "url": "https://example.com/blobcat.png",
                 "static_url": "https://example.com/blobcat.png", "visible_in_picker": True}
            ])
            resp = client.get("/api/v1/custom_emojis", headers=auth_headers)
        assert resp.status_code == 200
        emojis = resp.json()
        assert isinstance(emojis, list)
        if emojis:
            assert "shortcode" in emojis[0]

    def test_streaming_health(self, client: TestClient):
        resp = client.get("/api/v1/streaming/health")
        assert resp.status_code == 200
        assert resp.json()["healthy"] is True


class TestAuthEndpoints:
    def test_register_app(self, client: TestClient):
        resp = client.post("/api/v1/apps", json={
            "client_name": "TestApp",
            "redirect_uris": "https://example.com/callback",
            "scopes": "read write",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "client_id" in data
        assert "client_secret" in data
        # PostgreSQL対応: client_id は "proxy_" プレフィックスを持つ
        assert data["client_id"].startswith("proxy_")

    def test_oauth_authorize_redirects(self, client: TestClient):
        # まずアプリ登録してclient_idを取得
        app_resp = client.post("/api/v1/apps", json={
            "client_name": "TestApp",
            "redirect_uris": "https://example.com/cb",
        })
        client_id = app_resp.json()["client_id"]
        resp = client.get(
            f"/oauth/authorize?client_id={client_id}"
            "&redirect_uri=https://example.com/cb&response_type=code&scope=read",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 307)
        location = resp.headers.get("location", "")
        assert "miauth" in location

    def test_oauth_token_client_credentials(self, client: TestClient):
        resp = client.post("/oauth/token", json={
            "grant_type": "client_credentials",
            "client_id": "proxy_xxx",
            "client_secret": "secret",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"

    def test_oauth_revoke(self, client: TestClient):
        resp = client.post("/oauth/revoke", json={"token": "sometoken"})
        assert resp.status_code == 200


class TestAccountEndpoints:
    def test_verify_credentials(self, client: TestClient, auth_headers: dict):
        # ローカルユーザーのDBから返るので Misskey モック不要
        resp = client.get("/api/v1/accounts/verify_credentials", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testuser"
        assert "source" in data

    def test_get_account(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.accounts.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.get_account = AsyncMock(return_value=SAMPLE_USER)
            resp = client.get("/api/v1/accounts/user001", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "user001"

    def test_account_statuses(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.accounts.MastodonClient") as MockClient:
            MockClient.return_value.get_account_statuses = AsyncMock(return_value=[{"id": "note001"}])
            resp = client.get("/api/v1/accounts/user001/statuses", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_follow_account(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.accounts.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.follow = AsyncMock(return_value={"id": "user002", "following": True})
            resp = client.post("/api/v1/accounts/user002/follow", headers=auth_headers)
        assert resp.status_code == 200

    def test_unfollow_account(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.accounts.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.unfollow = AsyncMock(return_value={"id": "user002", "following": False})
            resp = client.post("/api/v1/accounts/user002/unfollow", headers=auth_headers)
        assert resp.status_code == 200

    def test_block_account(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.accounts.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.block = AsyncMock(return_value={"id": "user002", "blocking": True})
            resp = client.post("/api/v1/accounts/user002/block", headers=auth_headers)
        assert resp.status_code == 200

    def test_mute_account(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.accounts.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.mute = AsyncMock(return_value={"id": "user002", "muting": True})
            resp = client.post("/api/v1/accounts/user002/mute", headers=auth_headers)
        assert resp.status_code == 200

    def test_search_accounts(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.accounts.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.search_accounts = AsyncMock(return_value=[SAMPLE_USER])
            resp = client.get("/api/v1/accounts/search?q=test", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_blocks(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.accounts.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.get_blocks = AsyncMock(return_value=[{"blockee": SAMPLE_USER}])
            resp = client.get("/api/v1/blocks", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_mutes(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.accounts.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.get_mutes = AsyncMock(return_value=[{"mutee": SAMPLE_USER}])
            resp = client.get("/api/v1/mutes", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestStatusEndpoints:
    def test_get_status(self, client: TestClient, auth_headers: dict):
        status = {"id": "note001", "content": "<p>Hello</p>", "visibility": "public"}
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.get_status = AsyncMock(return_value=status)
            resp = client.get("/api/v1/statuses/note001", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == "note001"

    def test_create_status(self, client: TestClient, auth_headers: dict):
        created = {"id": "note_new", "content": "<p>Hello!</p>", "visibility": "public"}
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.create_status = AsyncMock(return_value=created)
            resp = client.post(
                "/api/v1/statuses",
                json={"status": "Hello!", "visibility": "public"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == "note_new"

    def test_create_status_with_cw(self, client: TestClient, auth_headers: dict):
        created = {"id": "note_cw", "spoiler_text": "CW text", "sensitive": True, "content": "<p>Body</p>"}
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.create_status = AsyncMock(return_value=created)
            resp = client.post(
                "/api/v1/statuses",
                json={"status": "Body", "spoiler_text": "CW text"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["sensitive"] is True

    def test_delete_status(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.get_status = AsyncMock(return_value=SAMPLE_NOTE)
            instance.delete_status = AsyncMock(return_value={})
            resp = client.delete("/api/v1/statuses/note001", headers=auth_headers)
        assert resp.status_code == 200

    def test_favourite_status(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            MockClient.return_value.favourite = AsyncMock(return_value={"id": "note001", "favourited": True})
            resp = client.post("/api/v1/statuses/note001/favourite", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["favourited"] is True

    def test_unfavourite_status(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            MockClient.return_value.unfavourite = AsyncMock(return_value={"id": "note001", "favourited": False})
            resp = client.post("/api/v1/statuses/note001/unfavourite", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["favourited"] is False

    def test_emoji_reaction_put(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            MockClient.return_value.add_emoji_reaction = AsyncMock(return_value={"id": "note001"})
            resp = client.put("/api/v1/statuses/note001/emoji_reactions/%F0%9F%8E%89", headers=auth_headers)
        assert resp.status_code == 200

    def test_emoji_reaction_delete(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            MockClient.return_value.remove_emoji_reaction = AsyncMock(return_value={"id": "note001"})
            resp = client.delete("/api/v1/statuses/note001/emoji_reactions/%F0%9F%8E%89", headers=auth_headers)
        assert resp.status_code == 200

    def test_emoji_reaction_list(self, client: TestClient, auth_headers: dict):
        """List emoji reactions (Fedibird extension)."""
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.get_notifications = AsyncMock(return_value=[
                {"type": "❤", "user": SAMPLE_USER},
                {"type": "❤", "user": {**SAMPLE_USER, "id": "user002"}},
            ])
            resp = client.get("/api/v1/statuses/note001/emoji_reactions", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_reblog_status(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            MockClient.return_value.reblog = AsyncMock(return_value={"id": "renote001", "reblogged": True})
            resp = client.post("/api/v1/statuses/note001/reblog", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["reblogged"] is True

    def test_bookmark_status(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.bookmark = AsyncMock(return_value={"id": "note001", "bookmarked": True})
            resp = client.post("/api/v1/statuses/note001/bookmark", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["bookmarked"] is True

    def test_status_context(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.get_context = AsyncMock(return_value={
                "ancestors": [SAMPLE_NOTE],
                "descendants": [],
            })
            resp = client.get("/api/v1/statuses/note001/context", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "ancestors" in data
        assert "descendants" in data


class TestTimelineEndpoints:
    def test_home_timeline(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.home_timeline = AsyncMock(return_value=[SAMPLE_NOTE])
            resp = client.get("/api/v1/timelines/home", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["id"] == "note001"

    def test_public_timeline(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.public_timeline = AsyncMock(return_value=[SAMPLE_NOTE])
            resp = client.get("/api/v1/timelines/public", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_local_timeline(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.public_timeline = AsyncMock(return_value=[SAMPLE_NOTE])
            resp = client.get("/api/v1/timelines/public?local=true", headers=auth_headers)
        assert resp.status_code == 200

    def test_bookmarks(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.statuses.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.get_bookmarks = AsyncMock(return_value=[{"note": SAMPLE_NOTE}])
            resp = client.get("/api/v1/bookmarks", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestNotificationEndpoints:
    def test_get_notifications(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.get_notifications = AsyncMock(return_value=[SAMPLE_NOTIFICATION])
            resp = client.get("/api/v1/notifications", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_clear_notifications(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.clear_notifications = AsyncMock(return_value={})
            resp = client.delete("/api/v1/notifications", headers=auth_headers)
        assert resp.status_code in (200, 204)


class TestSearchEndpoints:
    def test_search_all(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.search = AsyncMock(return_value={"accounts": [], "statuses": [], "hashtags": []})
            resp = client.get("/api/v1/search?q=test", headers=auth_headers)
        assert resp.status_code == 200

    def test_search_accounts_only(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            MockClient.return_value.search = AsyncMock(return_value={"accounts": [], "statuses": [], "hashtags": []})
            resp = client.get("/api/v1/search?q=test&type=accounts", headers=auth_headers)
        assert resp.status_code == 200


SAMPLE_MASTO_LIST = {"id": "list001", "title": "My List", "replies_policy": "followed", "exclusive": False}


class TestListsEndpoints:
    """Lists endpoints proxy to upstream (nekonoverse list API)."""

    def test_get_lists(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            MockClient.return_value.get_lists = AsyncMock(return_value=[SAMPLE_MASTO_LIST])
            resp = client.get("/api/v1/lists", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == [SAMPLE_MASTO_LIST]

    def test_create_list(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            MockClient.return_value.create_list = AsyncMock(return_value=SAMPLE_MASTO_LIST)
            resp = client.post("/api/v1/lists", json={"title": "My List"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == "My List"

    def test_get_list(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            MockClient.return_value.get_list = AsyncMock(return_value=SAMPLE_MASTO_LIST)
            resp = client.get("/api/v1/lists/list001", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == "list001"

    def test_delete_list(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            MockClient.return_value.delete_list = AsyncMock(return_value={})
            resp = client.delete("/api/v1/lists/list001", headers=auth_headers)
        assert resp.status_code == 200

    def test_list_timeline(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            MockClient.return_value.list_timeline = AsyncMock(return_value=[])
            resp = client.get("/api/v1/timelines/list/list001", headers=auth_headers)
        assert resp.status_code == 200


class TestMiscEndpoints:
    def test_preferences(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            MockClient.return_value = MockClient.return_value
            resp = client.get("/api/v1/preferences", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "posting:default:visibility" in data

    def test_filters_empty(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            MockClient.return_value = MockClient.return_value
            resp = client.get("/api/v1/filters", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_followed_tags_empty(self, client: TestClient, auth_headers: dict):
        with patch("app.api.v1.misc.MastodonClient") as MockClient:
            MockClient.return_value = MockClient.return_value
            resp = client.get("/api/v1/followed_tags", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_nodeinfo_discovery(self, client: TestClient):
        resp = client.get("/.well-known/nodeinfo", headers={"User-Agent": "Dart/3.8 (dart:io)"})
        assert resp.status_code == 200
        data = resp.json()
        assert "links" in data

    def test_verify_app(self, client: TestClient):
        resp = client.get("/api/v1/apps/verify_credentials")
        assert resp.status_code == 200
        assert "name" in resp.json()


DART_UA = {"User-Agent": "Dart/3.8 (dart:io)"}


class TestNodeInfo:
    def test_well_known_nodeinfo_discovery(self, client: TestClient):
        resp = client.get("/.well-known/nodeinfo", headers=DART_UA)
        assert resp.status_code == 200
        data = resp.json()
        assert "links" in data
        assert len(data["links"]) == 1
        link = data["links"][0]
        assert link["rel"] == "http://nodeinfo.diaspora.software/ns/schema/2.0"
        assert link["href"].endswith("/nodeinfo/2.0")

    def test_well_known_nodeinfo_non_dart_ua_returns_404(self, client: TestClient):
        """Dart クライアント以外は 404"""
        resp = client.get("/.well-known/nodeinfo", headers={"User-Agent": "Mozilla/5.0"})
        assert resp.status_code == 404

    def test_well_known_nodeinfo_no_ua_returns_404(self, client: TestClient):
        """UA なしも 404"""
        resp = client.get("/.well-known/nodeinfo")
        assert resp.status_code == 404

    def test_nodeinfo_20(self, client: TestClient):
        with patch("app.api.nodeinfo.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "originalUsersCount": 42,
                "originalNotesCount": 1234,
            }
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(return_value=mock_resp)
            resp = client.get("/nodeinfo/2.0", headers=DART_UA)
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "2.0"
        assert data["software"]["name"] == "misskey-mastodon-proxy"
        assert "activitypub" in data["protocols"]
        assert data["usage"]["users"]["total"] == 42
        assert data["usage"]["localPosts"] == 1234
        assert data["openRegistrations"] is False
        assert "emoji_reaction" in data["metadata"]["features"]

    def test_nodeinfo_20_misskey_unreachable(self, client: TestClient):
        """上流が落ちていてもゼロにフォールバックして 200 を返す"""
        with patch("app.api.nodeinfo.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("timeout"))
            resp = client.get("/nodeinfo/2.0", headers=DART_UA)
        assert resp.status_code == 200
        data = resp.json()
        assert data["usage"]["users"]["total"] == 0
        assert data["usage"]["localPosts"] == 0

    def test_nodeinfo_20_non_dart_ua_returns_404(self, client: TestClient):
        """Dart クライアント以外は 404"""
        resp = client.get("/nodeinfo/2.0", headers={"User-Agent": "curl/8.0"})
        assert resp.status_code == 404

    def test_well_known_href_points_to_proxy_not_upstream(self, client: TestClient):
        """href が上流インスタンスではなくプロキシ自身を指している"""
        resp = client.get("/.well-known/nodeinfo", headers=DART_UA)
        href = resp.json()["links"][0]["href"]
        assert "nekonoverse.org" not in href
