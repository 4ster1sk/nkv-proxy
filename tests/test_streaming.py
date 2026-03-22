"""Tests for streaming event conversion."""
import json
import pytest
from app.services.streaming import _mk_event_to_mastodon
from tests.conftest import SAMPLE_NOTE, SAMPLE_NOTIFICATION

INSTANCE_URL = "https://misskey.example.com"


class TestStreamingEventConversion:
    def test_note_event_becomes_update(self):
        result = _mk_event_to_mastodon("note", SAMPLE_NOTE, INSTANCE_URL)
        assert result is not None
        event, payload = result
        assert event == "update"
        data = json.loads(payload)
        assert data["id"] == "note001"
        assert "emoji_reactions" in data

    def test_notification_event(self):
        result = _mk_event_to_mastodon("notification", SAMPLE_NOTIFICATION, INSTANCE_URL)
        assert result is not None
        event, payload = result
        assert event == "notification"
        data = json.loads(payload)
        assert data["type"] == "emoji_reaction"

    def test_reaction_event_fedibird(self):
        reaction_body = {
            "id": "note001",
            "reaction": "❤",
            "count": 5,
            "user": {"id": "user001", "username": "testuser"},
        }
        result = _mk_event_to_mastodon("reaction", reaction_body, INSTANCE_URL)
        assert result is not None
        event, payload = result
        assert event == "status.updated"
        data = json.loads(payload)
        assert "emoji_reaction" in data
        assert data["emoji_reaction"]["name"] == "❤"

    def test_unread_notifications_count_skipped(self):
        result = _mk_event_to_mastodon("unreadNotificationsCount", {"count": 3}, INSTANCE_URL)
        assert result is None

    def test_me_updated_skipped(self):
        result = _mk_event_to_mastodon("meUpdated", {}, INSTANCE_URL)
        assert result is None

    def test_follow_event_becomes_filters_changed(self):
        result = _mk_event_to_mastodon("follow", {}, INSTANCE_URL)
        assert result is not None
        event, _ = result
        assert event == "filters_changed"

    def test_unknown_event_type(self):
        result = _mk_event_to_mastodon("someUnknownEvent", {}, INSTANCE_URL)
        assert result is None

    def test_reaction_event_custom_emoji(self):
        reaction_body = {
            "id": "note001",
            "reaction": ":sparkles@remote.example:",
            "count": 2,
        }
        result = _mk_event_to_mastodon("reaction", reaction_body, INSTANCE_URL)
        assert result is not None
        event, payload = result
        data = json.loads(payload)
        assert "emoji_reaction" in data
        assert "sparkles" in data["emoji_reaction"]["name"]

    def test_note_event_payload_has_fedibird_fields(self):
        result = _mk_event_to_mastodon("note", SAMPLE_NOTE, INSTANCE_URL)
        assert result is not None
        _, payload = result
        data = json.loads(payload)
        # Fedibird extension fields
        assert "emoji_reactions" in data
        assert isinstance(data["emoji_reactions"], list)
