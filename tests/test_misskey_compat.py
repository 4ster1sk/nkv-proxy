"""Tests for Misskey-compatible API endpoints ( POST /api/... )."""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from tests.conftest import SAMPLE_NOTIFICATION

AUTH_BODY = {"i": "test_access_token_fixed"}

# Mastodon フォーマットのサンプルデータ
MASTO_ACCOUNT = {
    "id": "user001",
    "username": "testuser",
    "display_name": "Test User",
    "locked": False,
    "bot": False,
    "created_at": "2023-01-01T00:00:00.000Z",
    "note": "<p>A test user</p>",
    "url": "https://nekonoverse.org/@testuser",
    "avatar": "https://example.com/avatar.png",
    "avatar_static": "https://example.com/avatar.png",
    "header": None,
    "header_static": None,
    "followers_count": 10,
    "following_count": 5,
    "statuses_count": 100,
    "fields": [],
    "emojis": [],
}

MASTO_STATUS = {
    "id": "note001",
    "created_at": "2023-06-01T12:00:00.000Z",
    "content": "<p>Hello, world!</p>",
    "spoiler_text": "",
    "visibility": "public",
    "sensitive": False,
    "uri": "https://nekonoverse.org/@testuser/note001",
    "url": "https://nekonoverse.org/@testuser/note001",
    "replies_count": 1,
    "reblogs_count": 2,
    "favourites_count": 3,
    "favourited": False,
    "reblogged": False,
    "bookmarked": False,
    "reblog": None,
    "in_reply_to_id": None,
    "poll": None,
    "media_attachments": [],
    "mentions": [],
    "tags": [],
    "emojis": [],
    "account": MASTO_ACCOUNT,
}

# 実際の /api/meta レスポンスを模したフィクスチャ
UPSTREAM_META = {
    "maintainerName": "admin",
    "maintainerEmail": "admin@example.com",
    "version": "2026.3.2-alpha.2",
    "providesTarball": False,
    "name": "Test Instance",
    "shortName": None,
    "uri": "https://misskey.example.com",
    "description": "Test server",
    "langs": ["ja"],
    "tosUrl": "",
    "repositoryUrl": "https://github.com/misskey-dev/misskey",
    "feedbackUrl": "https://github.com/misskey-dev/misskey/issues",
    "impressumUrl": "",
    "privacyPolicyUrl": "",
    "inquiryUrl": None,
    "disableRegistration": True,
    "emailRequiredForSignup": False,
    "enableHcaptcha": False,
    "hcaptchaSiteKey": None,
    "enableMcaptcha": False,
    "mcaptchaSiteKey": None,
    "mcaptchaInstanceUrl": None,
    "enableRecaptcha": False,
    "recaptchaSiteKey": None,
    "enableTurnstile": False,
    "turnstileSiteKey": None,
    "enableTestcaptcha": False,
    "googleAnalyticsMeasurementId": None,
    "swPublickey": "BDqzyfEjkTOis...",
    "themeColor": "#773894",
    "disableSignup": True,
    "serverChartsAuthRequired": True,
    "mascotImageUrl": "/assets/ai.png",
    "bannerUrl": "",
    "infoImageUrl": None,
    "serverErrorImageUrl": None,
    "notFoundImageUrl": None,
    "iconUrl": "https://example.com/icon.png",
    "backgroundImageUrl": None,
    "logoImageUrl": None,
    "maxNoteTextLength": 3000,
    "defaultLightTheme": "{\"id\":\"light\"}",
    "defaultDarkTheme": "{\"id\":\"dark\"}",
    "clientOptions": {
        "entrancePageStyle": "simple",
        "showTimelineForVisitor": False,
        "showActivitiesForVisitor": False,
    },
    "ads": [],
    "notesPerOneAd": 0,
    "enableEmail": False,
    "enableServiceWorker": True,
    "translatorAvailable": True,
    "serverRules": ["rule1", "rule2"],
    "policies": {
        "gtlAvailable": False,
        "ltlAvailable": False,
        "canPublicNote": True,
        "mentionLimit": 20,
        "canInvite": False,
        "inviteLimit": 0,
        "inviteLimitCycle": 10080,
        "inviteExpirationTime": 0,
        "canManageCustomEmojis": False,
        "canManageAvatarDecorations": False,
        "canSearchNotes": False,
        "canSearchUsers": True,
        "canUseTranslator": False,
        "canHideAds": False,
        "driveCapacityMb": 500,
        "maxFileSizeMb": 30,
        "alwaysMarkNsfw": False,
        "canUpdateBioMedia": True,
        "pinLimit": 5,
        "antennaLimit": 5,      # 上流は 5 → プロキシが 0 に上書き
        "antennaNotesLimit": 200,
        "wordMuteLimit": 200,
        "webhookLimit": 3,
        "clipLimit": 10,
        "noteEachClipsLimit": 200,
        "userListLimit": 10,
        "userEachUserListsLimit": 50,
        "rateLimitFactor": 1,
        "avatarDecorationLimit": 1,
        "canImportAntennas": False,
        "canImportBlocking": False,
        "canImportFollowing": False,
        "canImportMuting": False,
        "canImportUserLists": False,
        "chatAvailability": "available",
        "uploadableFileTypes": ["image/*", "video/*", "audio/*"],
        "noteDraftLimit": 10,
        "scheduledNoteLimit": 1,
        "watermarkAvailable": True,
        "fileSizeLimit": 50,
    },
    "sentryForFrontend": None,
    "mediaProxy": "https://misskey.example.com/proxy",
    "enableUrlPreview": True,
    "noteSearchableScope": "global",
    "federation": "all",
    "cacheRemoteFiles": False,
    "cacheRemoteSensitiveFiles": True,
    "requireSetup": False,
    "proxyAccountName": "proxy",
    "features": {
        "localTimeline": False,
        "globalTimeline": False,
        "registration": False,
        "emailRequiredForSignup": False,
        "hcaptcha": False,
        "recaptcha": False,
        "turnstile": False,
        "objectStorage": True,
        "serviceWorker": True,
        "miauth": True,
    },
}

# 実際の meta に含まれる全トップレベルキー（61フィールド）
EXPECTED_META_KEYS = {
    "maintainerName", "maintainerEmail", "version", "providesTarball",
    "name", "shortName", "uri", "description", "langs",
    "tosUrl", "repositoryUrl", "feedbackUrl", "impressumUrl",
    "privacyPolicyUrl", "inquiryUrl",
    "disableRegistration", "emailRequiredForSignup",
    "enableHcaptcha", "hcaptchaSiteKey",
    "enableMcaptcha", "mcaptchaSiteKey", "mcaptchaInstanceUrl",
    "enableRecaptcha", "recaptchaSiteKey",
    "enableTurnstile", "turnstileSiteKey",
    "enableTestcaptcha", "googleAnalyticsMeasurementId",
    "swPublickey", "themeColor", "disableSignup", "serverChartsAuthRequired",
    "mascotImageUrl", "bannerUrl", "infoImageUrl", "serverErrorImageUrl",
    "notFoundImageUrl", "iconUrl", "backgroundImageUrl", "logoImageUrl",
    "maxNoteTextLength", "defaultLightTheme", "defaultDarkTheme",
    "clientOptions", "ads", "notesPerOneAd",
    "enableEmail", "enableServiceWorker", "translatorAvailable",
    "serverRules", "policies", "sentryForFrontend",
    "mediaProxy", "enableUrlPreview",
    "noteSearchableScope", "federation",
    "cacheRemoteFiles", "cacheRemoteSensitiveFiles",
    "requireSetup", "proxyAccountName", "features",
}

EXPECTED_POLICIES_KEYS = {
    "gtlAvailable", "ltlAvailable", "canPublicNote", "mentionLimit",
    "canInvite", "inviteLimit", "inviteLimitCycle", "inviteExpirationTime",
    "canManageCustomEmojis", "canManageAvatarDecorations",
    "canSearchNotes", "canSearchUsers", "canUseTranslator", "canHideAds",
    "driveCapacityMb", "maxFileSizeMb", "alwaysMarkNsfw", "canUpdateBioMedia",
    "pinLimit", "antennaLimit", "antennaNotesLimit",
    "wordMuteLimit", "webhookLimit", "clipLimit", "noteEachClipsLimit",
    "userListLimit", "userEachUserListsLimit", "rateLimitFactor",
    "avatarDecorationLimit",
    "canImportAntennas", "canImportBlocking", "canImportFollowing",
    "canImportMuting", "canImportUserLists",
    "chatAvailability", "uploadableFileTypes",
    "noteDraftLimit", "scheduledNoteLimit", "watermarkAvailable", "fileSizeLimit",
}

EXPECTED_FEATURES_KEYS = {
    "localTimeline", "globalTimeline", "registration", "emailRequiredForSignup",
    "hcaptcha", "recaptcha", "turnstile", "objectStorage", "serviceWorker", "miauth",
}

EXPECTED_CLIENT_OPTIONS_KEYS = {
    "entrancePageStyle", "showTimelineForVisitor", "showActivitiesForVisitor",
}


def _make_mock_meta(client_mock, response=None):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = response if response is not None else UPSTREAM_META
    client_mock.return_value.__aenter__ = AsyncMock(return_value=client_mock.return_value)
    client_mock.return_value.__aexit__ = AsyncMock(return_value=False)
    client_mock.return_value.post = AsyncMock(return_value=mock_resp)


class TestMisskeyCompatMetaStructure:
    """実際の /api/meta レスポンス構造との完全互換テスト"""

    def test_all_top_level_keys_present(self, client: TestClient):
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        assert resp.status_code == 200
        data = resp.json()
        missing = EXPECTED_META_KEYS - set(data.keys())
        assert not missing, f"Missing top-level keys: {missing}"

    def test_no_extra_unexpected_keys(self, client: TestClient):
        """予期しない余分なキーがないこと（厳密互換）"""
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        data = resp.json()
        extra = set(data.keys()) - EXPECTED_META_KEYS
        assert not extra, f"Unexpected extra keys: {extra}"

    def test_policies_all_keys_present(self, client: TestClient):
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        policies = resp.json()["policies"]
        missing = EXPECTED_POLICIES_KEYS - set(policies.keys())
        assert not missing, f"Missing policies keys: {missing}"

    def test_policies_no_extra_keys(self, client: TestClient):
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        policies = resp.json()["policies"]
        extra = set(policies.keys()) - EXPECTED_POLICIES_KEYS
        assert not extra, f"Unexpected policies keys: {extra}"

    def test_features_all_keys_present(self, client: TestClient):
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        features = resp.json()["features"]
        missing = EXPECTED_FEATURES_KEYS - set(features.keys())
        assert not missing, f"Missing features keys: {missing}"

    def test_client_options_all_keys_present(self, client: TestClient):
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        opts = resp.json()["clientOptions"]
        missing = EXPECTED_CLIENT_OPTIONS_KEYS - set(opts.keys())
        assert not missing, f"Missing clientOptions keys: {missing}"


class TestMisskeyCompatMetaValues:
    """重要フィールドの値検証"""

    def test_antenna_limit_overridden_to_zero(self, client: TestClient):
        """上流が antennaLimit=5 でもプロキシは必ず 0 を返す"""
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)  # upstream has antennaLimit=5
            resp = client.post("/api/meta", json={})
        assert resp.json()["policies"]["antennaLimit"] == 0

    def test_miauth_feature_always_true(self, client: TestClient):
        """miAuth は常に True"""
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient, response={**UPSTREAM_META,
                "features": {**UPSTREAM_META["features"], "miauth": False}})
            resp = client.post("/api/meta", json={})
        assert resp.json()["features"]["miauth"] is True

    def test_uri_matches_upstream(self, client: TestClient):
        """uri はスキームなしのホスト名"""
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        uri = resp.json()["uri"]
        # uri は上流の値をそのまま返す（実際の meta も https:// 付き）
        assert uri == "https://misskey.example.com"

    def test_version_from_upstream(self, client: TestClient):
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        assert resp.json()["version"] == "2026.3.2-alpha.2"

    def test_policies_types(self, client: TestClient):
        """policies の各フィールドの型チェック"""
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        p = resp.json()["policies"]
        # bool フィールド
        for key in ["gtlAvailable", "ltlAvailable", "canPublicNote", "canInvite",
                    "canManageCustomEmojis", "canSearchNotes", "canSearchUsers",
                    "alwaysMarkNsfw", "canImportAntennas", "watermarkAvailable"]:
            assert isinstance(p[key], bool), f"policies.{key} should be bool"
        # int フィールド
        for key in ["mentionLimit", "inviteLimit", "driveCapacityMb",
                    "antennaLimit", "pinLimit", "fileSizeLimit"]:
            assert isinstance(p[key], int), f"policies.{key} should be int"
        # list フィールド
        assert isinstance(p["uploadableFileTypes"], list)

    def test_ads_is_list(self, client: TestClient):
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        assert isinstance(resp.json()["ads"], list)

    def test_server_rules_is_list(self, client: TestClient):
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        assert isinstance(resp.json()["serverRules"], list)

    def test_langs_is_list(self, client: TestClient):
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        assert isinstance(resp.json()["langs"], list)

    def test_upstream_values_passed_through(self, client: TestClient):
        """上流の値がそのまま反映される"""
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            _make_mock_meta(MockClient)
            resp = client.post("/api/meta", json={})
        data = resp.json()
        assert data["maxNoteTextLength"] == 3000
        assert data["enableServiceWorker"] is True
        assert data["themeColor"] == "#773894"
        assert data["mediaProxy"] == "https://misskey.example.com/proxy"
        assert data["noteSearchableScope"] == "global"
        assert data["federation"] == "all"
        assert data["cacheRemoteFiles"] is False
        assert data["cacheRemoteSensitiveFiles"] is True
        assert data["clientOptions"]["entrancePageStyle"] == "simple"

    def test_upstream_unreachable_fallback_has_all_keys(self, client: TestClient):
        """Misskey が落ちていても全 61 フィールドを返す"""
        with patch("app.api.misskey_compat.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(side_effect=Exception("timeout"))
            resp = client.post("/api/meta", json={})
        assert resp.status_code == 200
        data = resp.json()
        missing = EXPECTED_META_KEYS - set(data.keys())
        assert not missing, f"Fallback missing keys: {missing}"
        # フォールバック時もアンテナは 0
        assert data["policies"]["antennaLimit"] == 0
        # フォールバック時も miauth は True
        assert data["features"]["miauth"] is True


class TestMisskeyCompatStats:
    def test_api_stats(self, client: TestClient):
        with patch("app.api.misskey_compat._forward", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = {"originalUsersCount": 100, "originalNotesCount": 5000}
            resp = client.post("/api/stats", json={})
        assert resp.status_code == 200

    def test_api_stats_fallback_on_error(self, client: TestClient):
        with patch("app.api.misskey_compat._forward", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.side_effect = Exception("unreachable")
            resp = client.post("/api/stats", json={})
        assert resp.status_code == 200
        assert resp.json()["notesCount"] == 0


class TestMisskeyCompatI:
    """
    /api/i は MastodonClient.verify_credentials() に変換して返す。
    conftest の testuser は mastodon_token 設定済みの前提。
    """

    def test_api_i_returns_user(self, client: TestClient):
        masto_account = {
            "id": "user001", "username": "testuser", "display_name": "Test User",
            "locked": False, "bot": False, "created_at": "2023-01-01T00:00:00Z",
            "note": "", "url": "https://nekonoverse.org/@testuser",
            "avatar": "https://example.com/avatar.png", "header": None,
            "followers_count": 10, "following_count": 5, "statuses_count": 100,
            "fields": [],
        }
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.verify_credentials = AsyncMock(return_value=masto_account)
            resp = client.post("/api/i", json=AUTH_BODY)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testuser"
        assert "followersCount" in data

    def test_api_i_no_token_returns_401(self, client: TestClient):
        resp = client.post("/api/i", json={})
        assert resp.status_code == 401

    def test_api_i_bearer_header(self, client: TestClient):
        masto_account = {
            "id": "user001", "username": "testuser", "display_name": "Test User",
            "locked": False, "bot": False, "created_at": "2023-01-01T00:00:00Z",
            "note": "", "url": "https://nekonoverse.org/@testuser",
            "avatar": None, "header": None,
            "followers_count": 0, "following_count": 0, "statuses_count": 0,
            "fields": [],
        }
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.verify_credentials = AsyncMock(return_value=masto_account)
            resp = client.post("/api/i", json={},
                               headers={"Authorization": f"Bearer {AUTH_BODY['i']}"})
        assert resp.status_code == 200

    def test_api_i_update(self, client: TestClient):
        masto_account = {
            "id": "user001", "username": "testuser", "display_name": "New Name",
            "locked": False, "bot": False, "created_at": "2023-01-01T00:00:00Z",
            "note": "", "url": "https://nekonoverse.org/@testuser",
            "avatar": None, "header": None,
            "followers_count": 0, "following_count": 0, "statuses_count": 0,
            "fields": [],
        }
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.update_credentials = AsyncMock(return_value=masto_account)
            resp = client.post("/api/i/update", json={**AUTH_BODY, "name": "New Name"})
        assert resp.status_code == 200

    def test_api_i_notifications(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_notifications = AsyncMock(return_value=[SAMPLE_NOTIFICATION])
            resp = client.post("/api/i/notifications", json=AUTH_BODY)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestMisskeyCompatNotes:
    def test_api_notes_timeline(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.home_timeline = AsyncMock(return_value=[MASTO_STATUS])
            resp = client.post("/api/notes/timeline", json=AUTH_BODY)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["id"] == "note001"

    def test_api_notes_timeline_no_token_401(self, client: TestClient):
        resp = client.post("/api/notes/timeline", json={})
        assert resp.status_code == 401

    def test_api_notes_local_timeline(self, client: TestClient):
        with patch("app.api.misskey_compat.supports_local_timeline",
                   new=AsyncMock(return_value=True)):
            with patch("app.api.misskey_compat.MastodonClient") as MockClient:
                MockClient.return_value.public_timeline = AsyncMock(return_value=[MASTO_STATUS])
                resp = client.post("/api/notes/local-timeline", json=AUTH_BODY)
        assert resp.status_code == 200

    def test_api_notes_local_timeline_disabled(self, client: TestClient):
        """ENABLE_LOCAL_TIMELINE=false の場合は 400 を返す。"""
        with patch.object(
            __import__("app.core.config", fromlist=["settings"]).settings,
            "ENABLE_LOCAL_TIMELINE", "false"
        ):
            resp = client.post("/api/notes/local-timeline", json=AUTH_BODY)
        assert resp.status_code == 400

    def test_api_notes_local_timeline_auto_disabled(self, client: TestClient):
        """ENABLE_LOCAL_TIMELINE=auto で上流が LTL 非対応なら 400 を返す。"""
        with patch("app.api.misskey_compat.supports_local_timeline",
                   new=AsyncMock(return_value=False)):
            resp = client.post("/api/notes/local-timeline", json=AUTH_BODY)
        assert resp.status_code == 400

    def test_api_notes_global_timeline(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.public_timeline = AsyncMock(return_value=[MASTO_STATUS])
            resp = client.post("/api/notes/global-timeline", json=AUTH_BODY)
        assert resp.status_code == 200

    def test_api_notes_create(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.create_status = AsyncMock(return_value=MASTO_STATUS)
            resp = client.post("/api/notes/create", json={**AUTH_BODY, "text": "Hello!"})
        assert resp.status_code == 200
        assert "createdNote" in resp.json()

    def test_api_notes_delete(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.delete_status = AsyncMock(return_value={})
            resp = client.post("/api/notes/delete", json={**AUTH_BODY, "noteId": "note001"})
        assert resp.status_code == 200

    def test_api_notes_show(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_status = AsyncMock(return_value=MASTO_STATUS)
            resp = client.post("/api/notes/show", json={**AUTH_BODY, "noteId": "note001"})
        assert resp.status_code == 200
        assert resp.json()["id"] == "note001"

    def test_api_notes_search(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.search = AsyncMock(
                return_value={"statuses": [MASTO_STATUS], "accounts": [], "hashtags": []}
            )
            resp = client.post("/api/notes/search", json={**AUTH_BODY, "query": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["id"] == "note001"


class TestMisskeyCompatReactions:
    def test_api_reactions_create(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.add_emoji_reaction = AsyncMock(return_value=MASTO_STATUS)
            MockClient.return_value.favourite = AsyncMock(return_value=MASTO_STATUS)
            resp = client.post("/api/notes/reactions/create",
                               json={**AUTH_BODY, "noteId": "note001", "reaction": "❤"})
        assert resp.status_code == 200

    def test_api_reactions_create_no_token_401(self, client: TestClient):
        resp = client.post("/api/notes/reactions/create",
                           json={"noteId": "note001", "reaction": "❤"})
        assert resp.status_code == 401

    def test_api_reactions_delete(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.remove_emoji_reaction = AsyncMock(return_value=MASTO_STATUS)
            MockClient.return_value.unfavourite = AsyncMock(return_value=MASTO_STATUS)
            resp = client.post("/api/notes/reactions/delete",
                               json={**AUTH_BODY, "noteId": "note001"})
        assert resp.status_code == 200

    def test_api_reactions_list(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_status = AsyncMock(return_value={
                "id": "note001",
                "emoji_reactions": [{"name": "❤", "count": 1, "me": True, "account_ids": []}],
            })
            MockClient.return_value._get = AsyncMock(return_value=[])
            resp = client.post("/api/notes/reactions", json={**AUTH_BODY, "noteId": "note001"})
        assert resp.status_code == 200


class TestMisskeyCompatNotesCreate:
    """notes/create の media_ids=None 問題のテスト。"""

    def test_create_note_without_files(self, client: TestClient):
        """fileIds 未指定（None）でも 422 にならない。"""
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.create_status = AsyncMock(return_value=MASTO_STATUS)
            resp = client.post("/api/notes/create", json={
                **AUTH_BODY,
                "text": "Hello world",
                "visibility": "public",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "createdNote" in data
        assert data["createdNote"] is not None  # テキストはMASTO_STATUSから変換

    def test_create_note_with_cw(self, client: TestClient):
        """CW付きノートが spoiler_text として送られる。"""
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            instance = MockClient.return_value
            instance.create_status = AsyncMock(return_value=MASTO_STATUS)
            resp = client.post("/api/notes/create", json={
                **AUTH_BODY,
                "text": "本文",
                "cw": "CW: 注意",
            })
        assert resp.status_code == 200
        # create_status に spoiler_text が渡されていること
        call_kwargs = instance.create_status.call_args[1]
        assert call_kwargs.get("spoiler_text") == "CW: 注意"

    def test_create_note_media_ids_none_not_sent(self, client: TestClient):
        """fileIds=None のとき media_ids が Mastodon に送られない。"""
        from app.services.mastodon_client import MastodonClient as RealClient
        captured = {}

        async def mock_post(self, path, json=None, data=None):
            captured["json"] = json
            return MASTO_STATUS

        with patch.object(RealClient, "_post", mock_post):
            with patch("app.api.misskey_compat.MastodonClient") as MockClient:
                instance = MockClient.return_value
                instance.create_status = AsyncMock(return_value=MASTO_STATUS)
                resp = client.post("/api/notes/create", json={
                    **AUTH_BODY, "text": "no files",
                })
        assert resp.status_code == 200
        # create_status が None の media_ids なしで呼ばれていること
        call_kwargs = instance.create_status.call_args[1]
        assert call_kwargs.get("media_ids") is None  # 渡されていないか None


class TestMisskeyCompatUsers:
    def test_api_users_show_by_id(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_account = AsyncMock(return_value=MASTO_ACCOUNT)
            resp = client.post("/api/users/show", json={**AUTH_BODY, "userId": "user001"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "testuser"

    def test_api_users_show_by_username(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.search_accounts = AsyncMock(return_value=[MASTO_ACCOUNT])
            resp = client.post("/api/users/show", json={**AUTH_BODY, "username": "testuser"})
        assert resp.status_code == 200

    def test_api_users_search(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.search_accounts = AsyncMock(return_value=[MASTO_ACCOUNT])
            resp = client.post("/api/users/search", json={**AUTH_BODY, "query": "test"})
        assert resp.status_code == 200

    def test_api_users_followers(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.verify_credentials = AsyncMock(
                return_value={**MASTO_ACCOUNT, "id": "viewer001"}
            )
            MockClient.return_value.get_followers = AsyncMock(return_value=[MASTO_ACCOUNT])
            resp = client.post("/api/users/followers", json={**AUTH_BODY, "userId": "user001"})
        assert resp.status_code == 200

    def test_api_users_following(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.verify_credentials = AsyncMock(
                return_value={**MASTO_ACCOUNT, "id": "viewer001"}
            )
            MockClient.return_value.get_following = AsyncMock(return_value=[MASTO_ACCOUNT])
            resp = client.post("/api/users/following", json={**AUTH_BODY, "userId": "user001"})
        assert resp.status_code == 200


class TestMisskeyCompatFollowRelationship:
    """following/followers レスポンスに createdAt/followerId/followeeId が含まれる。"""

    def test_following_has_required_fields(self, client: TestClient):
        """following レスポンスに Misskey 互換フィールドが含まれる。"""
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.verify_credentials = AsyncMock(
                return_value={**MASTO_ACCOUNT, "id": "viewer001"}  # id を後で指定して上書き確定
            )
            MockClient.return_value.get_following = AsyncMock(
                return_value=[MASTO_ACCOUNT]
            )
            resp = client.post("/api/users/following", json={**AUTH_BODY, "userId": "user001"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        item = data[0]
        assert "id" in item
        assert "createdAt" in item
        assert "followeeId" in item
        assert "followerId" in item
        assert "followee" in item
        # following なので followerId = viewer, followeeId = account
        assert item["followerId"] == "viewer001"
        assert item["followeeId"] == "user001"
        assert item["followee"] is not None
        assert item["follower"] is None

    def test_followers_has_required_fields(self, client: TestClient):
        """followers レスポンスに Misskey 互換フィールドが含まれる。"""
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.verify_credentials = AsyncMock(
                return_value={**MASTO_ACCOUNT, "id": "viewer001"}  # id を後で指定して上書き確定
            )
            MockClient.return_value.get_followers = AsyncMock(
                return_value=[MASTO_ACCOUNT]
            )
            resp = client.post("/api/users/followers", json={**AUTH_BODY, "userId": "user001"})
        assert resp.status_code == 200
        data = resp.json()
        item = data[0]
        # followers: account(user001) が viewer(viewer001) をフォローしている
        # followerId = フォローした側(account), followeeId = フォローされた側(viewer)
        assert item["followerId"] == "user001"
        assert item["followeeId"] == "viewer001"
        assert item["follower"] is not None
        assert item["followee"] is None

    def test_following_id_is_deterministic(self, client: TestClient):
        """同じペアなら常に同じ id が生成される。"""
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.verify_credentials = AsyncMock(
                return_value={**MASTO_ACCOUNT, "id": "viewer001"}  # id を後で指定して上書き確定
            )
            MockClient.return_value.get_following = AsyncMock(
                return_value=[MASTO_ACCOUNT]
            )
            resp1 = client.post("/api/users/following", json={**AUTH_BODY, "userId": "user001"})
            resp2 = client.post("/api/users/following", json={**AUTH_BODY, "userId": "user001"})
        assert resp1.json()[0]["id"] == resp2.json()[0]["id"]


class TestMisskeyCompatFollowing:
    def test_api_following_create(self, client: TestClient):
        with patch("app.api.misskey_compat.MisskeyClient") as MockClient:
            instance = MockClient.return_value
            instance.follow = AsyncMock(return_value={})
            resp = client.post("/api/following/create",
                               json={**AUTH_BODY, "userId": "user002"})
        assert resp.status_code == 200

    def test_api_following_delete(self, client: TestClient):
        with patch("app.api.misskey_compat.MisskeyClient") as MockClient:
            instance = MockClient.return_value
            instance.unfollow = AsyncMock(return_value={})
            resp = client.post("/api/following/delete",
                               json={**AUTH_BODY, "userId": "user002"})
        assert resp.status_code == 200

    def test_api_following_no_token_401(self, client: TestClient):
        resp = client.post("/api/following/create", json={"userId": "user002"})
        assert resp.status_code == 401


class TestMisskeyCompatBlocking:
    def test_api_blocking_create(self, client: TestClient):
        with patch("app.api.misskey_compat.MisskeyClient") as MockClient:
            instance = MockClient.return_value
            instance.block = AsyncMock(return_value={})
            resp = client.post("/api/blocking/create",
                               json={**AUTH_BODY, "userId": "user002"})
        assert resp.status_code == 200

    def test_api_blocking_list(self, client: TestClient):
        with patch("app.api.misskey_compat.MisskeyClient") as MockClient:
            instance = MockClient.return_value
            instance.get_blocks = AsyncMock(return_value=[])
            resp = client.post("/api/blocking/list", json=AUTH_BODY)
        assert resp.status_code == 200


class TestMisskeyCompatMuting:
    def test_api_muting_create(self, client: TestClient):
        with patch("app.api.misskey_compat.MisskeyClient") as MockClient:
            instance = MockClient.return_value
            instance.mute = AsyncMock(return_value={})
            resp = client.post("/api/muting/create",
                               json={**AUTH_BODY, "userId": "user002"})
        assert resp.status_code == 200

    def test_api_muting_list(self, client: TestClient):
        with patch("app.api.misskey_compat.MisskeyClient") as MockClient:
            instance = MockClient.return_value
            instance.get_mutes = AsyncMock(return_value=[])
            resp = client.post("/api/muting/list", json=AUTH_BODY)
        assert resp.status_code == 200


class TestBuildReactionKey:
    """_build_reaction_key ヘルパーのユニットテスト"""

    def test_unicode_emoji(self):
        from app.services.note_converter import _build_reaction_key
        rkey, url = _build_reaction_key({"name": "❤", "count": 1})
        assert rkey == "❤"
        assert url is None

    def test_unicode_zwj_emoji(self):
        from app.services.note_converter import _build_reaction_key
        rkey, url = _build_reaction_key({"name": "👨‍👩‍👧‍👦", "count": 1})
        assert rkey == "👨‍👩‍👧‍👦"
        assert url is None

    def test_local_custom_emoji_nekonoverse_style(self):
        """Nekonoverse は :name: 形式で返す"""
        from app.services.note_converter import _build_reaction_key
        rkey, url = _build_reaction_key({
            "name": ":awesome:",
            "url": "https://example.com/emoji/awesome.png",
            "count": 2,
        })
        assert rkey == ":awesome:"
        assert url == "https://example.com/emoji/awesome.png"

    def test_remote_custom_emoji_nekonoverse_style(self):
        """Nekonoverse は :name@domain: 形式で返す"""
        from app.services.note_converter import _build_reaction_key
        rkey, url = _build_reaction_key({
            "name": ":blobcat@remote.host:",
            "url": "https://remote.host/emoji/blobcat.png",
            "count": 1,
        })
        assert rkey == ":blobcat@remote.host:"
        assert url == "https://remote.host/emoji/blobcat.png"

    def test_local_custom_emoji_shortcode_only(self):
        """他サーバーは name="shortcode" (コロンなし) で返す"""
        from app.services.note_converter import _build_reaction_key
        rkey, url = _build_reaction_key({
            "name": "awesome",
            "url": "https://example.com/emoji/awesome.png",
            "count": 2,
        })
        assert rkey == ":awesome:"
        assert url == "https://example.com/emoji/awesome.png"

    def test_remote_custom_emoji_with_domain_field(self):
        """name="shortcode", domain="remote.host" の形式"""
        from app.services.note_converter import _build_reaction_key
        rkey, url = _build_reaction_key({
            "name": "blobcat",
            "domain": "remote.host",
            "url": "https://remote.host/emoji/blobcat.png",
            "count": 1,
        })
        assert rkey == ":blobcat@remote.host:"
        assert url == "https://remote.host/emoji/blobcat.png"

    def test_empty_name(self):
        from app.services.note_converter import _build_reaction_key
        rkey, url = _build_reaction_key({"name": "", "count": 1})
        assert rkey == ""
        assert url is None


class TestNoteConverterReactionEmojis:
    """reactionEmojis が正しく構築されるかテスト"""

    def test_reaction_emojis_for_custom_emoji(self):
        from app.services.note_converter import masto_status_to_mk_note
        status = {
            **MASTO_STATUS,
            "emoji_reactions": [
                {"name": ":awesome:", "count": 2, "me": False,
                 "url": "https://example.com/emoji/awesome.png"},
                {"name": "❤", "count": 1, "me": True},
            ],
        }
        note = masto_status_to_mk_note(status)
        assert note["reactions"] == {":awesome:": 2, "❤": 1}
        assert note["reactionEmojis"] == {"awesome": "https://example.com/emoji/awesome.png"}
        assert note["reactionCount"] == 3
        assert note["myReaction"] == "❤"

    def test_reaction_emojis_for_remote_custom(self):
        from app.services.note_converter import masto_status_to_mk_note
        status = {
            **MASTO_STATUS,
            "emoji_reactions": [
                {"name": "blobcat", "domain": "remote.host", "count": 1,
                 "url": "https://remote.host/emoji/blobcat.png", "me": True},
            ],
        }
        note = masto_status_to_mk_note(status)
        assert ":blobcat@remote.host:" in note["reactions"]
        assert note["reactions"][":blobcat@remote.host:"] == 1
        assert note["reactionEmojis"]["blobcat@remote.host"] == "https://remote.host/emoji/blobcat.png"
        assert note["myReaction"] == ":blobcat@remote.host:"

    def test_reaction_emojis_empty_for_unicode_only(self):
        from app.services.note_converter import masto_status_to_mk_note
        status = {
            **MASTO_STATUS,
            "emoji_reactions": [
                {"name": "❤", "count": 3, "me": False},
                {"name": "👍", "count": 1, "me": False},
            ],
        }
        note = masto_status_to_mk_note(status)
        assert note["reactionEmojis"] == {}

    def test_favourites_count_fallback(self):
        from app.services.note_converter import masto_status_to_mk_note
        status = {**MASTO_STATUS, "favourites_count": 5, "favourited": True}
        note = masto_status_to_mk_note(status)
        assert note["reactions"] == {"❤": 5}
        assert note["myReaction"] == "❤"
        assert note["reactionEmojis"] == {}


class TestReactionsListRemoteEmoji:
    """/api/notes/reactions がリモート絵文字のキーを正しく返すテスト"""

    def test_reactions_list_uses_build_reaction_key(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_status = AsyncMock(return_value={
                "id": "note001",
                "emoji_reactions": [
                    {"name": "blobcat", "domain": "remote.host", "count": 1,
                     "url": "https://remote.host/emoji/blobcat.png",
                     "account_ids": ["user001"]},
                ],
            })
            resp = client.post("/api/notes/reactions", json={**AUTH_BODY, "noteId": "note001"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["reaction"] == ":blobcat@remote.host:"

    def test_reactions_list_nekonoverse_format(self, client: TestClient):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_status = AsyncMock(return_value={
                "id": "note001",
                "emoji_reactions": [
                    {"name": ":awesome:", "count": 2, "url": "https://example.com/awesome.png"},
                ],
            })
            resp = client.post("/api/notes/reactions", json={**AUTH_BODY, "noteId": "note001"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(r["reaction"] == ":awesome:" for r in data)


class TestMisskeyCompatMiAuth:
    """
    /api/miauth/{session_id}/check はDB直接参照に変わった。
    未認可セッション → ok: false、存在しない → ok: false
    """

    def test_api_miauth_check_unknown_session_returns_not_ok(self, client: TestClient):
        """存在しないセッションはok: falseを返す（404ではない）"""
        resp = client.post("/api/miauth/00000000-0000-0000-0000-000000000000/check")
        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    def test_api_miauth_check_unauthorized_session_returns_not_ok(self, client: TestClient):
        """authorized=falseのセッションはok: falseを返す"""
        resp = client.post("/api/miauth/11111111-1111-1111-1111-111111111111/check")
        assert resp.status_code == 200
        assert resp.json()["ok"] is False


class TestUsersShow:
    REMOTE_ACCOUNT = {
        "id": "remote001",
        "username": "remoteuser",
        "display_name": "Remote User",
        "acct": "remoteuser@remote.example.com",
        "locked": False,
        "bot": False,
        "created_at": "2023-01-01T00:00:00.000Z",
        "note": "",
        "url": "https://remote.example.com/@remoteuser",
        "avatar": "https://remote.example.com/avatar.png",
        "avatar_static": "https://remote.example.com/avatar.png",
        "header": None,
        "followers_count": 5,
        "following_count": 3,
        "statuses_count": 20,
        "fields": [],
        "emojis": [],
    }

    def test_users_show_by_userid(self, client):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_account = AsyncMock(return_value=self.REMOTE_ACCOUNT)
            resp = client.post("/api/users/show", json={**AUTH_BODY, "userId": "remote001"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["host"] == "remote.example.com"

    def test_users_show_by_username_and_host(self, client):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.search_accounts = AsyncMock(return_value=[self.REMOTE_ACCOUNT])
            resp = client.post("/api/users/show", json={
                **AUTH_BODY,
                "username": "remoteuser",
                "host": "remote.example.com",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["host"] == "remote.example.com"
        MockClient.return_value.search_accounts.assert_called_once_with(
            "remoteuser@remote.example.com", limit=1
        )

    def test_users_show_by_username_only(self, client):
        local_account = {**self.REMOTE_ACCOUNT, "acct": "remoteuser", "id": "local001"}
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.search_accounts = AsyncMock(return_value=[local_account])
            resp = client.post("/api/users/show", json={**AUTH_BODY, "username": "remoteuser"})
        assert resp.status_code == 200
        MockClient.return_value.search_accounts.assert_called_once_with("remoteuser", limit=1)


class TestUserListsAPI:
    MASTO_LIST = {"id": "list001", "title": "Friends", "replies_policy": "followed", "exclusive": False}

    def test_lists_list(self, client):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_lists = AsyncMock(return_value=[self.MASTO_LIST])
            resp = client.post("/api/users/lists/list", json=AUTH_BODY)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "list001"
        assert data[0]["name"] == "Friends"

    def test_lists_create(self, client):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.create_list = AsyncMock(return_value=self.MASTO_LIST)
            resp = client.post("/api/users/lists/create", json={**AUTH_BODY, "name": "Friends"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Friends"

    def test_lists_show(self, client):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_list = AsyncMock(return_value=self.MASTO_LIST)
            resp = client.post("/api/users/lists/show", json={**AUTH_BODY, "listId": "list001"})
        assert resp.status_code == 200
        assert resp.json()["id"] == "list001"

    def test_lists_delete(self, client):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.delete_list = AsyncMock(return_value={})
            resp = client.post("/api/users/lists/delete", json={**AUTH_BODY, "listId": "list001"})
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_lists_push(self, client):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.add_list_accounts = AsyncMock(return_value={})
            resp = client.post("/api/users/lists/push", json={**AUTH_BODY, "listId": "list001", "userId": "user001"})
        assert resp.status_code == 200
        MockClient.return_value.add_list_accounts.assert_called_once_with("list001", ["user001"])

    def test_lists_pull(self, client):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.remove_list_accounts = AsyncMock(return_value={})
            resp = client.post("/api/users/lists/pull", json={**AUTH_BODY, "listId": "list001", "userId": "user001"})
        assert resp.status_code == 200
        MockClient.return_value.remove_list_accounts.assert_called_once_with("list001", ["user001"])

    def test_user_list_timeline(self, client):
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.list_timeline = AsyncMock(return_value=[MASTO_STATUS])
            resp = client.post("/api/notes/user-list-timeline", json={**AUTH_BODY, "listId": "list001"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "note001"

    def test_lists_show_missing_list_id(self, client):
        """listId 省略で 400 を返す。"""
        resp = client.post("/api/users/lists/show", json={**AUTH_BODY})
        assert resp.status_code == 400

    def test_lists_update_missing_list_id(self, client):
        """listId 省略で 400 を返す。"""
        resp = client.post("/api/users/lists/update", json={**AUTH_BODY, "name": "new"})
        assert resp.status_code == 400

    def test_lists_delete_missing_list_id(self, client):
        """listId 省略で 400 を返す。"""
        resp = client.post("/api/users/lists/delete", json={**AUTH_BODY})
        assert resp.status_code == 400

    def test_lists_push_missing_list_id(self, client):
        """listId 省略で 400 を返す。"""
        resp = client.post("/api/users/lists/push", json={**AUTH_BODY, "userId": "user001"})
        assert resp.status_code == 400

    def test_lists_pull_missing_list_id(self, client):
        """listId 省略で 400 を返す。"""
        resp = client.post("/api/users/lists/pull", json={**AUTH_BODY, "userId": "user001"})
        assert resp.status_code == 400

    def test_lists_get_memberships_missing_list_id(self, client):
        """listId 省略で 400 を返す。"""
        resp = client.post("/api/users/lists/get-memberships", json={**AUTH_BODY})
        assert resp.status_code == 400

    def test_user_list_timeline_missing_list_id(self, client):
        """listId 省略で 400 を返す。"""
        resp = client.post("/api/notes/user-list-timeline", json={**AUTH_BODY})
        assert resp.status_code == 400


class TestNotesState:

    def test_notes_state_basic(self, client):
        """bookmarked/muted が正しくマップされる。"""
        status = {**MASTO_STATUS, "bookmarked": True, "muted": True}
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_status = AsyncMock(return_value=status)
            resp = client.post("/api/notes/state", json={**AUTH_BODY, "noteId": "note001"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["isFavorited"] is True
        assert data["isMutedThread"] is True
        assert data["isWatching"] is False

    def test_notes_state_not_favorited(self, client):
        """bookmarked=False の場合は isFavorited=False。"""
        status = {**MASTO_STATUS, "bookmarked": False, "muted": False}
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_status = AsyncMock(return_value=status)
            resp = client.post("/api/notes/state", json={**AUTH_BODY, "noteId": "note001"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["isFavorited"] is False
        assert data["isMutedThread"] is False
        assert data["isWatching"] is False

    def test_notes_state_missing_note_id(self, client):
        """noteId 省略は 400 を返す。"""
        resp = client.post("/api/notes/state", json={**AUTH_BODY})
        assert resp.status_code == 400

    def test_notes_state_no_token(self, client):
        """トークンなしは 401 を返す。"""
        resp = client.post("/api/notes/state", json={"noteId": "note001"})
        assert resp.status_code == 401


class TestApShow:

    def test_ap_show_note(self, client):
        """URI がノートに解決される場合 type=Note を返す。"""
        uri = "https://nekonoverse.org/@testuser/note001"
        search_result = {"statuses": [MASTO_STATUS], "accounts": [], "hashtags": []}
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.search = AsyncMock(return_value=search_result)
            resp = client.post("/api/ap/show", json={**AUTH_BODY, "uri": uri})
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "Note"
        assert data["object"]["id"] == "note001"

    def test_ap_show_user(self, client):
        """URI がユーザーに解決される場合 type=User を返す。"""
        uri = "https://nekonoverse.org/@testuser"
        search_result = {"statuses": [], "accounts": [MASTO_ACCOUNT], "hashtags": []}
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.search = AsyncMock(return_value=search_result)
            resp = client.post("/api/ap/show", json={**AUTH_BODY, "uri": uri})
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "User"
        assert data["object"]["username"] == "testuser"

    def test_ap_show_not_found(self, client):
        """解決できない URI は 404 を返す。"""
        search_result = {"statuses": [], "accounts": [], "hashtags": []}
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.search = AsyncMock(return_value=search_result)
            resp = client.post("/api/ap/show", json={**AUTH_BODY, "uri": "https://example.com/unknown"})
        assert resp.status_code == 404

    def test_ap_show_missing_uri(self, client):
        """uri を省略すると 400 を返す。"""
        resp = client.post("/api/ap/show", json={**AUTH_BODY})
        assert resp.status_code == 400

    def test_ap_show_no_token(self, client):
        """トークンなしは 401 を返す。"""
        resp = client.post("/api/ap/show", json={"uri": "https://nekonoverse.org/@testuser"})
        assert resp.status_code == 401


class TestIFavorites:

    def test_i_favorites_returns_notes(self, client):
        """ブックマーク一覧をノート配列で返す。"""
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_bookmarks = AsyncMock(return_value=[MASTO_STATUS])
            resp = client.post("/api/i/favorites", json={**AUTH_BODY})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "note001"
        assert data[0]["noteId"] == data[0]["id"]

    def test_i_favorites_empty(self, client):
        """ブックマークが空の場合は空配列を返す。"""
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_bookmarks = AsyncMock(return_value=[])
            resp = client.post("/api/i/favorites", json={**AUTH_BODY})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_i_favorites_pagination(self, client):
        """sinceId / untilId が min_id / max_id に変換される。"""
        with patch("app.api.misskey_compat.MastodonClient") as MockClient:
            MockClient.return_value.get_bookmarks = AsyncMock(return_value=[])
            resp = client.post("/api/i/favorites", json={
                **AUTH_BODY, "sinceId": "abc", "untilId": "xyz", "limit": 5,
            })
            call_kwargs = MockClient.return_value.get_bookmarks.call_args
        assert resp.status_code == 200
        assert call_kwargs.kwargs.get("min_id") == "abc"
        assert call_kwargs.kwargs.get("max_id") == "xyz"

    def test_i_favorites_no_token(self, client):
        """トークンなしは 401 を返す。"""
        resp = client.post("/api/i/favorites", json={})
        assert resp.status_code == 401
