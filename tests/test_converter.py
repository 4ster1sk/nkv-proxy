"""Tests for Misskey → Mastodon conversion logic."""
from app.services.converter import (
    build_reaction_summary,
    fedibird_reaction_to_misskey,
    misskey_reaction_to_fedibird,
    mk_note_to_status,
    mk_notification_to_mastodon,
    mk_user_to_account,
)
from app.services.note_converter import masto_notification_to_mk
from app.services.user_converter import masto_to_misskey_user_detailed, masto_to_misskey_user_lite
from tests.conftest import SAMPLE_NOTE, SAMPLE_NOTIFICATION, SAMPLE_USER

INSTANCE_URL = "https://misskey.example.com"


class TestReactionConversion:
    def test_unicode_emoji_to_fedibird(self):
        result = misskey_reaction_to_fedibird("❤")
        assert result.startswith(":") and result.endswith(":")

    def test_local_custom_emoji(self):
        result = misskey_reaction_to_fedibird(":awesome:")
        assert result == ":awesome:"

    def test_remote_custom_emoji(self):
        result = misskey_reaction_to_fedibird(":awesome@remote.host:")
        assert result == ":awesome@remote.host:"

    def test_fedibird_to_misskey_passthrough(self):
        result = fedibird_reaction_to_misskey(":heart:")
        assert result == ":heart:"

    def test_build_reaction_summary_unicode(self):
        reactions = {"❤": 5}
        summary = build_reaction_summary(reactions)
        assert len(summary) == 1
        assert summary[0]["count"] == 5
        assert "name" in summary[0]

    def test_build_reaction_summary_custom(self):
        reactions = {":awesome:": 2, ":wave@remote.example:": 1}
        summary = build_reaction_summary(reactions)
        assert len(summary) == 2
        remote = next(s for s in summary if "domain" in s)
        assert remote["domain"] == "remote.example"
        assert remote["name"] == "wave"

    def test_build_reaction_summary_mixed(self):
        reactions = {"❤": 3, ":star:": 1}
        summary = build_reaction_summary(reactions)
        assert len(summary) == 2
        total = sum(s["count"] for s in summary)
        assert total == 4


class TestUserConversion:
    def test_basic_user(self):
        account = mk_user_to_account(SAMPLE_USER, INSTANCE_URL)
        assert account["id"] == "user001"
        assert account["username"] == "testuser"
        assert account["acct"] == "testuser"  # local user, no host
        assert account["display_name"] == "Test User"
        assert account["followers_count"] == 10
        assert account["following_count"] == 5
        assert account["statuses_count"] == 100
        assert account["locked"] is False
        assert account["bot"] is False

    def test_remote_user(self):
        remote_user = {**SAMPLE_USER, "host": "remote.example.com"}
        account = mk_user_to_account(remote_user, INSTANCE_URL)
        assert account["acct"] == "testuser@remote.example.com"

    def test_user_with_fields(self):
        user = {**SAMPLE_USER, "fields": [{"name": "Website", "value": "https://example.com"}]}
        account = mk_user_to_account(user, INSTANCE_URL)
        assert len(account["fields"]) == 1
        assert account["fields"][0]["name"] == "Website"

    def test_user_without_name(self):
        user = {**SAMPLE_USER, "name": None}
        account = mk_user_to_account(user, INSTANCE_URL)
        assert account["display_name"] == "testuser"

    def test_pleroma_extension(self):
        account = mk_user_to_account(SAMPLE_USER, INSTANCE_URL)
        assert "pleroma" in account
        assert account["pleroma"]["is_admin"] is False


class TestNoteConversion:
    def test_basic_note(self):
        status = mk_note_to_status(SAMPLE_NOTE, INSTANCE_URL)
        assert status["id"] == "note001"
        assert "Hello, world!" in status["content"]
        assert status["visibility"] == "public"
        assert status["sensitive"] is False
        assert status["spoiler_text"] == ""
        assert status["reblogs_count"] == 2
        assert status["replies_count"] == 1

    def test_visibility_mapping(self):
        for mk_vis, masto_vis in [
            ("public", "public"),
            ("home", "unlisted"),
            ("followers", "private"),
            ("specified", "direct"),
        ]:
            note = {**SAMPLE_NOTE, "visibility": mk_vis}
            status = mk_note_to_status(note, INSTANCE_URL)
            assert status["visibility"] == masto_vis

    def test_cw_note(self):
        note = {**SAMPLE_NOTE, "cw": "Content Warning", "text": "Sensitive content"}
        status = mk_note_to_status(note, INSTANCE_URL)
        assert status["sensitive"] is True
        assert status["spoiler_text"] == "Content Warning"

    def test_emoji_reactions_fedibird(self):
        status = mk_note_to_status(SAMPLE_NOTE, INSTANCE_URL)
        assert "emoji_reactions" in status
        assert len(status["emoji_reactions"]) == 2
        # ❤ should appear with count 3
        heart = next((r for r in status["emoji_reactions"] if r["count"] == 3), None)
        assert heart is not None

    def test_pure_renote_is_reblog(self):
        renote = {
            **SAMPLE_NOTE,
            "id": "renote001",
            "text": None,
            "renote": SAMPLE_NOTE,
            "renoteId": "note001",
        }
        status = mk_note_to_status(renote, INSTANCE_URL)
        assert status["reblog"] is not None
        assert status["reblog"]["id"] == "note001"

    def test_favourites_count_is_sum_of_reactions(self):
        status = mk_note_to_status(SAMPLE_NOTE, INSTANCE_URL)
        # reactions: {"❤": 3, ":awesome:": 1} → total 4
        assert status["favourites_count"] == 4


class TestNotificationConversion:
    def test_reaction_notification(self):
        notif = mk_notification_to_mastodon(SAMPLE_NOTIFICATION, INSTANCE_URL)
        assert notif["type"] == "emoji_reaction"
        assert notif["id"] == "notif001"
        assert "emoji" in notif

    def test_follow_notification(self):
        follow_notif = {
            **SAMPLE_NOTIFICATION,
            "type": "follow",
            "note": None,
            "reaction": None,
        }
        notif = mk_notification_to_mastodon(follow_notif, INSTANCE_URL)
        assert notif["type"] == "follow"

    def test_mention_notification(self):
        mention_notif = {**SAMPLE_NOTIFICATION, "type": "mention", "reaction": None}
        notif = mk_notification_to_mastodon(mention_notif, INSTANCE_URL)
        assert notif["type"] == "mention"

    def test_unknown_notification_returns_empty(self):
        unknown = {**SAMPLE_NOTIFICATION, "type": "achievementEarned"}
        notif = mk_notification_to_mastodon(unknown, INSTANCE_URL)
        assert notif == {}


MASTO_ACCOUNT = {
    "id": "muser001",
    "username": "mastouser",
    "display_name": "Masto User",
    "acct": "mastouser",
    "avatar": "https://example.com/avatar.png",
    "bot": False,
}

MASTO_STATUS = {
    "id": "mstatus001",
    "created_at": "2024-01-01T00:00:00.000Z",
    "content": "<p>Hello</p>",
    "spoiler_text": "",
    "visibility": "public",
    "sensitive": False,
    "in_reply_to_id": None,
    "replies_count": 0, "reblogs_count": 0, "favourites_count": 0,
    "favourited": False, "reblogged": False, "bookmarked": False,
    "reblog": None, "poll": None,
    "media_attachments": [], "mentions": [], "tags": [], "emojis": [],
    "account": MASTO_ACCOUNT,
}

MASTO_NOTIFICATION = {
    "id": "mnotif001",
    "type": "favourite",
    "created_at": "2024-06-01T10:00:00.000Z",
    "account": MASTO_ACCOUNT,
    "status": MASTO_STATUS,
}


class TestMastoNotificationToMk:
    def test_favourite_maps_to_reaction(self):
        result = masto_notification_to_mk(MASTO_NOTIFICATION)
        assert result is not None
        assert result["type"] == "reaction"
        assert result["reaction"] == "❤"

    def test_fedibird_emoji_reaction(self):
        notif = {**MASTO_NOTIFICATION, "type": "emoji_reaction", "emoji": ":blobcat:"}
        result = masto_notification_to_mk(notif)
        assert result is not None
        assert result["type"] == "reaction"
        assert result["reaction"] == ":blobcat:"

    def test_reblog_maps_to_renote(self):
        notif = {**MASTO_NOTIFICATION, "type": "reblog"}
        result = masto_notification_to_mk(notif)
        assert result is not None
        assert result["type"] == "renote"

    def test_follow_maps_to_follow(self):
        notif = {**MASTO_NOTIFICATION, "type": "follow", "status": None}
        result = masto_notification_to_mk(notif)
        assert result is not None
        assert result["type"] == "follow"
        assert result.get("note") is None

    def test_mention_without_reply_maps_to_mention(self):
        notif = {**MASTO_NOTIFICATION, "type": "mention"}
        result = masto_notification_to_mk(notif)
        assert result is not None
        assert result["type"] == "mention"

    def test_mention_with_in_reply_to_maps_to_reply(self):
        reply_status = {**MASTO_STATUS, "in_reply_to_id": "original001"}
        notif = {**MASTO_NOTIFICATION, "type": "mention", "status": reply_status}
        result = masto_notification_to_mk(notif)
        assert result is not None
        assert result["type"] == "reply"

    def test_follow_request_maps(self):
        notif = {**MASTO_NOTIFICATION, "type": "follow_request", "status": None}
        result = masto_notification_to_mk(notif)
        assert result is not None
        assert result["type"] == "receiveFollowRequest"

    def test_poll_maps_to_poll_ended(self):
        notif = {**MASTO_NOTIFICATION, "type": "poll"}
        result = masto_notification_to_mk(notif)
        assert result is not None
        assert result["type"] == "pollEnded"

    def test_unsupported_type_returns_none(self):
        notif = {**MASTO_NOTIFICATION, "type": "admin.sign_up"}
        assert masto_notification_to_mk(notif) is None

    def test_status_type_returns_none(self):
        notif = {**MASTO_NOTIFICATION, "type": "status"}
        assert masto_notification_to_mk(notif) is None

    def test_has_required_fields(self):
        result = masto_notification_to_mk(MASTO_NOTIFICATION)
        assert result is not None
        assert result["id"] == "mnotif001"
        assert result["createdAt"] == "2024-06-01T10:00:00.000Z"
        assert result["userId"] == "muser001"
        assert result["user"]["username"] == "mastouser"
        assert "isRead" in result
        assert "note" in result

    def test_note_is_converted(self):
        result = masto_notification_to_mk(MASTO_NOTIFICATION)
        assert result is not None
        assert result["note"]["id"] == "mstatus001"


class TestUserConverter:
    LOCAL_ACCOUNT = {
        "id": "local001",
        "username": "localuser",
        "display_name": "Local User",
        "acct": "localuser",
        "avatar": "https://example.com/avatar.png",
        "bot": False,
        "note": "",
        "fields": [],
        "locked": False,
        "followers_count": 0,
        "following_count": 0,
        "statuses_count": 0,
        "created_at": "2023-01-01T00:00:00.000Z",
    }
    REMOTE_ACCOUNT = {
        **LOCAL_ACCOUNT,
        "id": "remote001",
        "username": "remoteuser",
        "acct": "remoteuser@remote.example.com",
        "url": "https://remote.example.com/@remoteuser",
    }

    def test_local_user_host_is_none(self):
        result = masto_to_misskey_user_lite(self.LOCAL_ACCOUNT)
        assert result["host"] is None

    def test_remote_user_host_extracted_from_acct(self):
        result = masto_to_misskey_user_lite(self.REMOTE_ACCOUNT)
        assert result["host"] == "remote.example.com"

    def test_remote_user_instance_is_not_none(self):
        result = masto_to_misskey_user_lite(self.REMOTE_ACCOUNT)
        assert result["instance"] is not None

    def test_local_user_instance_is_none(self):
        result = masto_to_misskey_user_lite(self.LOCAL_ACCOUNT)
        assert result["instance"] is None

    def test_domain_field_fallback(self):
        """acct に @ がなくても domain フィールドがあれば host を返す"""
        account = {**self.LOCAL_ACCOUNT, "domain": "fallback.example.com"}
        result = masto_to_misskey_user_lite(account)
        assert result["host"] == "fallback.example.com"

    def test_detailed_remote_user_host(self):
        result = masto_to_misskey_user_detailed(self.REMOTE_ACCOUNT)
        assert result["host"] == "remote.example.com"
