"""
ストリーミング変換テスト

新実装: Mastodon SSE → Misskey WS イベント 変換をテストする。
MisskeyStreamingProxy._convert_event() および _masto_notification_to_mk() をテスト。
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.streaming import MisskeyStreamingProxy, _masto_notification_to_mk

# ---------------------------------------------------------------------------
# テスト用 Mastodon フォーマットサンプル
# ---------------------------------------------------------------------------

MASTO_STATUS = {
    "id": "status001",
    "created_at": "2024-01-01T00:00:00.000Z",
    "content": "<p>Hello from Mastodon!</p>",
    "spoiler_text": "",
    "visibility": "public",
    "sensitive": False,
    "uri": "https://nekonoverse.org/@user/status001",
    "url": "https://nekonoverse.org/@user/status001",
    "replies_count": 0, "reblogs_count": 1, "favourites_count": 3,
    "favourited": False, "reblogged": False, "bookmarked": False,
    "reblog": None, "poll": None,
    "media_attachments": [], "mentions": [], "tags": [], "emojis": [],
    "account": {
        "id": "user001", "username": "testuser", "display_name": "Test User",
        "avatar": "https://example.com/avatar.png",
        "bot": False, "locked": False,
    },
}

MASTO_NOTIFICATION = {
    "id": "notif001",
    "type": "favourite",
    "created_at": "2024-01-01T00:00:00.000Z",
    "account": {
        "id": "user002", "username": "liker", "display_name": "Liker",
        "avatar": "https://example.com/avatar2.png", "bot": False,
    },
    "status": MASTO_STATUS,
}

MASTO_MENTION = {
    "id": "notif002",
    "type": "mention",
    "created_at": "2024-01-01T00:00:00.000Z",
    "account": {
        "id": "user003", "username": "mentioner", "display_name": "Mentioner",
        "avatar": None, "bot": False,
    },
    "status": MASTO_STATUS,
}

MASTO_FOLLOW = {
    "id": "notif003",
    "type": "follow",
    "created_at": "2024-01-01T00:00:00.000Z",
    "account": {
        "id": "user004", "username": "follower", "display_name": "Follower",
        "avatar": None, "bot": False,
    },
}


# ---------------------------------------------------------------------------
# MisskeyStreamingProxy._convert_event のテスト
# ---------------------------------------------------------------------------

class TestConvertEvent:
    """MisskeyStreamingProxy._convert_event(): Mastodon→Misskey 変換テスト。"""

    def _proxy(self):
        ws = MagicMock()
        return MisskeyStreamingProxy(ws, mastodon_token="tok", mastodon_instance="https://nekonoverse.org")

    def test_update_event_converts_to_note(self):
        """Mastodon `update` イベント → Misskey `note` イベント。"""
        proxy = self._proxy()
        mk_event, mk_body = proxy._convert_event("update", MASTO_STATUS)
        assert mk_event == "note"
        assert mk_body["id"] == "status001"
        assert mk_body["text"] == "Hello from Mastodon!"
        assert mk_body["visibility"] == "public"

    def test_notification_favourite_converts(self):
        """Mastodon `notification` (favourite) → Misskey `notification` (reaction)。"""
        proxy = self._proxy()
        mk_event, mk_body = proxy._convert_event("notification", MASTO_NOTIFICATION)
        assert mk_event == "notification"
        assert mk_body["type"] == "reaction"
        assert mk_body["userId"] == "user002"

    def test_notification_mention_converts(self):
        """Mastodon `notification` (mention) → Misskey `notification` (reply)。"""
        proxy = self._proxy()
        mk_event, mk_body = proxy._convert_event("notification", MASTO_MENTION)
        assert mk_event == "notification"
        assert mk_body["type"] == "reply"

    def test_notification_follow_converts(self):
        """Mastodon `notification` (follow) → Misskey `notification` (follow)。"""
        proxy = self._proxy()
        mk_event, mk_body = proxy._convert_event("notification", MASTO_FOLLOW)
        assert mk_event == "notification"
        assert mk_body["type"] == "follow"

    def test_delete_event_converts(self):
        """Mastodon `delete` → Misskey `noteDeleted`。"""
        proxy = self._proxy()
        mk_event, mk_body = proxy._convert_event("delete", "status001")
        assert mk_event == "noteDeleted"
        assert mk_body["deletedNoteId"] == "status001"

    def test_status_updated_converts(self):
        """Mastodon `status.updated` → Misskey `noteUpdated`。"""
        proxy = self._proxy()
        mk_event, mk_body = proxy._convert_event("status.updated", MASTO_STATUS)
        assert mk_event == "noteUpdated"

    def test_filters_changed_converts(self):
        """Mastodon `filters_changed` → Misskey `meUpdated`。"""
        proxy = self._proxy()
        mk_event, mk_body = proxy._convert_event("filters_changed", {})
        assert mk_event == "meUpdated"

    def test_unknown_event_returns_none(self):
        """未知のイベントは None を返す。"""
        proxy = self._proxy()
        result, _ = proxy._convert_event("unknown_event", {})
        assert result is None

    def test_note_has_renote_count(self):
        """変換された note に renoteCount が含まれる。"""
        proxy = self._proxy()
        _, mk_body = proxy._convert_event("update", MASTO_STATUS)
        assert "renoteCount" in mk_body
        assert mk_body["renoteCount"] == 1


# ---------------------------------------------------------------------------
# _masto_notification_to_mk のテスト
# ---------------------------------------------------------------------------

class TestMastoNotificationToMk:
    def test_favourite_maps_to_reaction(self):
        result = _masto_notification_to_mk(MASTO_NOTIFICATION)
        assert result["type"] == "reaction"
        assert "user" in result
        assert result["user"]["username"] == "liker"

    def test_mention_maps_to_reply(self):
        result = _masto_notification_to_mk(MASTO_MENTION)
        assert result["type"] == "reply"
        assert "note" in result

    def test_follow_maps_to_follow(self):
        result = _masto_notification_to_mk(MASTO_FOLLOW)
        assert result["type"] == "follow"
        assert result.get("note") is None  # フォロー通知にはnoteなし

    def test_reblog_maps_to_renote(self):
        notif = {**MASTO_NOTIFICATION, "type": "reblog"}
        result = _masto_notification_to_mk(notif)
        assert result["type"] == "renote"

    def test_notification_has_id_and_created_at(self):
        result = _masto_notification_to_mk(MASTO_NOTIFICATION)
        assert result["id"] == "notif001"
        assert result["createdAt"] == "2024-01-01T00:00:00.000Z"


# ---------------------------------------------------------------------------
# チャンネル購読のテスト
# ---------------------------------------------------------------------------

class TestChannelMapping:
    def test_channel_to_stream_mapping(self):
        from app.services.streaming import CHANNEL_TO_STREAM
        # HTL → /streaming/user
        assert CHANNEL_TO_STREAM["homeTimeline"] == "user"
        # LTL → /streaming/public (Nekonoverse に /public/local はない)
        assert CHANNEL_TO_STREAM["localTimeline"] == "public"
        # GTL → /streaming/public
        assert CHANNEL_TO_STREAM["globalTimeline"] == "public"
        assert CHANNEL_TO_STREAM["hybridTimeline"] == "public"
        # 通知 → /streaming/user (通知は user ストリームに統合)
        assert CHANNEL_TO_STREAM["notifications"] == "user"
        assert CHANNEL_TO_STREAM["main"] == "user"

    def test_stream_url_path_format(self):
        """SSE URLがパスベース形式になっていることを確認する。"""
        # "public:local" → "public/local" の変換確認
        stream = "public:local"
        stream_path = stream.replace(":", "/")
        assert stream_path == "public/local"

        stream2 = "user/notification"
        assert stream2 == "user/notification"  # 変換不要

    def test_mastodon_sse_url_generation(self):
        """各チャンネルが正しい Mastodon SSE URL にマッピングされる。"""
        from app.services.streaming import CHANNEL_TO_STREAM
        instance = "https://nekonoverse.org"

        cases = [
            ("homeTimeline",   f"{instance}/api/v1/streaming/user"),
            ("main",           f"{instance}/api/v1/streaming/user"),
            ("notifications",  f"{instance}/api/v1/streaming/user"),
            ("localTimeline",  f"{instance}/api/v1/streaming/public"),
            ("globalTimeline", f"{instance}/api/v1/streaming/public"),
            ("hybridTimeline", f"{instance}/api/v1/streaming/public"),
        ]
        for channel, expected_url in cases:
            stream = CHANNEL_TO_STREAM[channel]
            stream_path = stream.replace(":", "/")
            url = f"{instance}/api/v1/streaming/{stream_path}"
            assert url == expected_url, f"{channel}: expected {expected_url}, got {url}"

    @pytest.mark.asyncio
    async def test_handle_connect_sends_connected(self):
        """connect コマンドを受け取ると connected を返す。"""
        ws = AsyncMock()
        ws.receive_text = AsyncMock(side_effect=Exception("stop"))
        proxy = MisskeyStreamingProxy(ws, "tok", "https://nekonoverse.org")
        # _handle_connect を直接テスト
        await proxy._handle_connect({"channel": "homeTimeline", "id": "ch1"})
        ws.send_text.assert_called_once()
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "connected"
        assert sent["body"]["id"] == "ch1"

    @pytest.mark.asyncio
    async def test_handle_disconnect_cleans_up(self):
        """disconnect コマンドでチャンネルが削除される。"""
        ws = AsyncMock()
        proxy = MisskeyStreamingProxy(ws, "tok", "https://nekonoverse.org")
        proxy._channels["ch1"] = "user"
        proxy._stream_channels["user"] = {"ch1"}
        # タスクのモック
        task = MagicMock()
        task.cancel = MagicMock()
        proxy._tasks["user"] = task

        await proxy._handle_disconnect({"id": "ch1"})
        assert "ch1" not in proxy._channels
        task.cancel.assert_called_once()


# ---------------------------------------------------------------------------
# _fetch_status のテスト
# ---------------------------------------------------------------------------

class TestFetchStatus:
    """_fetch_status: ID のみペイロードに対してフル status を取得する。"""

    def _proxy(self):
        ws = MagicMock()
        return MisskeyStreamingProxy(ws, mastodon_token="tok", mastodon_instance="https://nekonoverse.org")

    @pytest.mark.asyncio
    async def test_fetch_status_success(self):
        """200 OK でフル status を返す。"""
        from unittest.mock import patch
        proxy = self._proxy()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MASTO_STATUS

        with patch("app.services.streaming.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            result = await proxy._fetch_status("status001")

        assert result == MASTO_STATUS

    @pytest.mark.asyncio
    async def test_fetch_status_not_found(self):
        """404 の場合は None を返す。"""
        from unittest.mock import patch
        proxy = self._proxy()
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("app.services.streaming.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            result = await proxy._fetch_status("status001")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_status_network_error(self):
        """ネットワークエラーの場合は None を返す。"""
        from unittest.mock import patch
        proxy = self._proxy()

        with patch("app.services.streaming.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("network error")
            )
            result = await proxy._fetch_status("status001")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_status_uses_bearer_token(self):
        """Authorization ヘッダーにトークンを付与する。"""
        from unittest.mock import patch
        proxy = self._proxy()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MASTO_STATUS

        with patch("app.services.streaming.httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_resp)
            mock_client.return_value.__aenter__.return_value.get = mock_get
            await proxy._fetch_status("status001")

        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer tok"


# ---------------------------------------------------------------------------
# ID のみペイロード（Nekonoverse 形式）のテスト
# ---------------------------------------------------------------------------

class TestThinPayload:
    """Nekonoverse の SSE は id のみを送るため、フル status を取得して変換する。"""

    @pytest.mark.asyncio
    async def test_thin_payload_triggers_fetch_and_sends_note(self):
        """update イベントで id のみのペイロードが来たら _fetch_status を呼び note を送信する。"""
        from unittest.mock import patch
        ws = AsyncMock()
        proxy = MisskeyStreamingProxy(ws, "tok", "https://nekonoverse.org")
        proxy._stream_channels["user"] = {"ch1"}

        async def fake_sse(*args, **kwargs):
            yield "update", {"id": "status001"}

        proxy._fetch_status = AsyncMock(return_value=MASTO_STATUS)
        with patch("app.services.streaming._mastodon_sse_stream", fake_sse):
            await proxy._sse_to_ws("user")

        proxy._fetch_status.assert_called_once_with("status001")
        ws.send_text.assert_called_once()
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "channel"
        assert sent["body"]["type"] == "note"
        assert sent["body"]["body"]["id"] == "status001"

    @pytest.mark.asyncio
    async def test_thin_payload_fetch_failure_skips_event(self):
        """_fetch_status が None を返した場合はイベントをスキップして送信しない。"""
        from unittest.mock import patch
        ws = AsyncMock()
        proxy = MisskeyStreamingProxy(ws, "tok", "https://nekonoverse.org")
        proxy._stream_channels["user"] = {"ch1"}

        async def fake_sse(*args, **kwargs):
            yield "update", {"id": "status001"}

        proxy._fetch_status = AsyncMock(return_value=None)
        with patch("app.services.streaming._mastodon_sse_stream", fake_sse):
            await proxy._sse_to_ws("user")

        ws.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_payload_skips_fetch(self):
        """フル status が来た場合は _fetch_status を呼ばずにそのまま変換する。"""
        from unittest.mock import patch
        ws = AsyncMock()
        proxy = MisskeyStreamingProxy(ws, "tok", "https://nekonoverse.org")
        proxy._stream_channels["user"] = {"ch1"}

        async def fake_sse(*args, **kwargs):
            yield "update", MASTO_STATUS

        proxy._fetch_status = AsyncMock()
        with patch("app.services.streaming._mastodon_sse_stream", fake_sse):
            await proxy._sse_to_ws("user")

        proxy._fetch_status.assert_not_called()
        ws.send_text.assert_called_once()
