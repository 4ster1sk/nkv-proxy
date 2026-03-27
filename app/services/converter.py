"""
Conversion helpers: Misskey API objects → Mastodon API objects.

Emoji reaction mapping follows Fedibird's convention:
  - Standard Unicode emoji → shortcode like ":heart:"
  - Custom emoji        → ":name@host:" (with host) or ":name:" (local)
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Emoji / Reaction helpers (Fedibird style)
# ---------------------------------------------------------------------------

def misskey_reaction_to_fedibird(reaction: str, host: str | None = None) -> str:
    """
    Convert a Misskey reaction string to a Fedibird-style emoji shortcode.

    Misskey reaction formats:
      - Unicode char(s): "❤", "👍"
      - Local custom:    ":name:"
      - Remote custom:   ":name@host:"

    Fedibird output:
      - Unicode → ":unicode_name:" using a simple mapping (pass-through for now)
      - Custom local  → ":name:"
      - Custom remote → ":name@host:"
    """
    if reaction.startswith(":") and reaction.endswith(":"):
        # Already in shortcode form (:name: or :name@host:)
        return reaction

    # Raw unicode emoji → wrap in colons as a shortcode (clients handle display)
    # Remove variation selectors
    cleaned = reaction.replace("\ufe0f", "").strip()
    return f":{cleaned}:"


def fedibird_reaction_to_misskey(shortcode: str) -> str:
    """
    Convert a Fedibird-style emoji shortcode back to Misskey reaction format.
    ":heart:" → ":heart:" (custom) or leave as-is for Unicode lookup.
    For simplicity we forward the shortcode directly; Misskey accepts :name: form.
    """
    return shortcode


def build_reaction_summary(reactions: dict[str, int]) -> list[dict]:
    """
    Build Mastodon-style emoji_reactions list (Fedibird extension) from
    Misskey's reactions dict {"❤️": 3, ":awesome@mi.tomadoi.com:": 1}.
    """
    result = []
    for reaction, count in reactions.items():
        shortcode = misskey_reaction_to_fedibird(reaction)
        # Determine if it's a custom emoji and extract name/url fields
        name = shortcode.strip(":")
        entry: dict[str, Any] = {
            "name": name,
            "count": count,
            "me": False,  # filled in per-user later
        }
        # Remote custom emoji: ":name@host:"
        if "@" in name:
            emoji_name, emoji_host = name.rsplit("@", 1)
            entry["name"] = emoji_name
            entry["domain"] = emoji_host
            entry["url"] = f"https://{emoji_host}/emoji/{emoji_name}.webp"
            entry["static_url"] = entry["url"]
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Account conversion
# ---------------------------------------------------------------------------

def mk_user_to_account(user: dict, instance_url: str) -> dict:
    host = user.get("host") or _extract_host(instance_url)
    acct = f"{user['username']}@{host}" if user.get("host") else user["username"]
    avatar = user.get("avatarUrl") or f"{instance_url}/identicon/{user['id']}"
    header = user.get("bannerUrl") or f"{instance_url}/static-assets/transparent.png"
    fields = [
        {"name": f["name"], "value": f["value"], "verified_at": None}
        for f in (user.get("fields") or [])
    ]
    emojis = _convert_emojis(user.get("emojis") or [])
    return {
        "id": user["id"],
        "username": user["username"],
        "acct": acct,
        "display_name": user.get("name") or user["username"],
        "locked": user.get("isLocked", False),
        "bot": user.get("isBot", False),
        "created_at": user.get("createdAt", ""),
        "note": user.get("description") or "",
        "url": f"{instance_url}/@{user['username']}",
        "avatar": avatar,
        "avatar_static": avatar,
        "header": header,
        "header_static": header,
        "followers_count": user.get("followersCount", 0),
        "following_count": user.get("followingCount", 0),
        "statuses_count": user.get("notesCount", 0),
        "last_status_at": None,
        "emojis": emojis,
        "fields": fields,
        # Fedibird / pleroma extensions
        "pleroma": {
            "is_admin": user.get("isAdmin", False),
            "is_moderator": user.get("isModerator", False),
        },
    }


# ---------------------------------------------------------------------------
# Note → Status conversion
# ---------------------------------------------------------------------------

def mk_note_to_status(note: dict, instance_url: str) -> dict:
    user = note.get("user", {})
    account = mk_user_to_account(user, instance_url)
    reblog = None
    if note.get("renote") and not note.get("text"):
        # Pure renote (boost)
        reblog = mk_note_to_status(note["renote"], instance_url)

    visibility_map = {
        "public": "public",
        "home": "unlisted",
        "followers": "private",
        "specified": "direct",
    }
    visibility = visibility_map.get(note.get("visibility", "public"), "public")

    media_attachments = _convert_files(note.get("files") or [])
    mentions = _convert_mentions(note.get("mentions") or [], instance_url)
    tags = _convert_tags(note.get("tags") or [])
    emojis = _convert_emojis(note.get("emojis") or [])

    reactions_raw = note.get("reactions") or {}
    emoji_reactions = build_reaction_summary(reactions_raw)

    # Poll
    poll = None
    if note.get("poll"):
        poll = _convert_poll(note["poll"], note["id"])

    return {
        "id": note["id"],
        "created_at": note.get("createdAt", ""),
        "in_reply_to_id": note.get("replyId"),
        "in_reply_to_account_id": None,
        "sensitive": note.get("cw") is not None,
        "spoiler_text": note.get("cw") or "",
        "visibility": visibility,
        "language": note.get("lang"),
        "uri": f"{instance_url}/notes/{note['id']}",
        "url": f"{instance_url}/notes/{note['id']}",
        "replies_count": note.get("repliesCount", 0),
        "reblogs_count": note.get("renoteCount", 0),
        "favourites_count": sum(reactions_raw.values()),
        "content": _mk_text_to_html(note.get("text") or ""),
        "reblog": reblog,
        "application": None,
        "account": account,
        "media_attachments": media_attachments,
        "mentions": mentions,
        "tags": tags,
        "emojis": emojis,
        "card": None,
        "poll": poll,
        # Fedibird extension: emoji_reactions
        "emoji_reactions": emoji_reactions,
        "favourited": False,
        "reblogged": False,
        "muted": False,
        "bookmarked": False,
        "pinned": False,
    }


# ---------------------------------------------------------------------------
# Notification conversion
# ---------------------------------------------------------------------------

def mk_notification_to_mastodon(notif: dict, instance_url: str) -> dict:
    type_map = {
        "follow": "follow",
        "mention": "mention",
        "reply": "mention",
        "renote": "reblog",
        "quote": "mention",
        "reaction": "emoji_reaction",  # Fedibird extension
        "pollEnded": "poll",
        "followRequestAccepted": "follow_request_accepted",
        "achievementEarned": None,
    }
    masto_type = type_map.get(notif.get("type", ""), "mention")
    if masto_type is None:
        return {}

    account = mk_user_to_account(notif["notifier"], instance_url) if notif.get("notifier") else None
    status = mk_note_to_status(notif["note"], instance_url) if notif.get("note") else None

    result: dict[str, Any] = {
        "id": notif["id"],
        "type": masto_type,
        "created_at": notif.get("createdAt", ""),
        "account": account,
        "status": status,
    }

    # Fedibird: emoji_reaction field
    if masto_type == "emoji_reaction" and notif.get("reaction"):
        result["emoji"] = misskey_reaction_to_fedibird(notif["reaction"])

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_host(instance_url: str) -> str:
    return instance_url.replace("https://", "").replace("http://", "").rstrip("/")


def _mk_text_to_html(text: str) -> str:
    if not text:
        return ""
    # Basic: wrap in <p>, convert newlines, linkify mentions/URLs
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # URLs
    text = re.sub(
        r"(https?://[^\s<>\"]+)",
        r'<a href="\1" target="_blank" rel="nofollow noopener noreferrer">\1</a>',
        text,
    )
    # @mention@host
    text = re.sub(
        r"@(\w+)@([\w.]+)",
        r'<a href="https://\2/@\1" class="mention">@\1@\2</a>',
        text,
    )
    paragraphs = text.split("\n\n")
    return "".join(f"<p>{p.replace(chr(10), '<br />')}</p>" for p in paragraphs if p)


def _convert_files(files: list[dict]) -> list[dict]:
    result = []
    for f in files:
        media_type = "unknown"
        mime = f.get("type", "")
        if mime.startswith("image/"):
            media_type = "image"
        elif mime.startswith("video/"):
            media_type = "video"
        elif mime.startswith("audio/"):
            media_type = "audio"
        elif mime.startswith("text/"):
            media_type = "unknown"

        result.append({
            "id": f["id"],
            "type": media_type,
            "url": f.get("url", ""),
            "preview_url": f.get("thumbnailUrl") or f.get("url", ""),
            "remote_url": f.get("url"),
            "text_url": f.get("url"),
            "meta": {
                "original": {
                    "width": f.get("properties", {}).get("width"),
                    "height": f.get("properties", {}).get("height"),
                }
            },
            "description": f.get("comment"),
            "blurhash": f.get("blurhash"),
        })
    return result


def _convert_mentions(mentions: list, instance_url: str) -> list[dict]:
    result = []
    for m in mentions:
        username = m if isinstance(m, str) else m.get("username", "")
        result.append({
            "id": "",
            "username": username,
            "url": f"{instance_url}/@{username}",
            "acct": username,
        })
    return result


def _convert_tags(tags: list) -> list[dict]:
    return [{"name": t, "url": ""} for t in tags]


def _convert_emojis(emojis: list | dict) -> list[dict]:
    if isinstance(emojis, dict):
        return [
            {"shortcode": name, "url": url, "static_url": url, "visible_in_picker": True}
            for name, url in emojis.items()
        ]
    return [
        {
            "shortcode": e.get("name", ""),
            "url": e.get("url", ""),
            "static_url": e.get("url", ""),
            "visible_in_picker": True,
        }
        for e in emojis
    ]


def _convert_poll(poll: dict, note_id: str) -> dict:
    options = [
        {"title": c.get("text", ""), "votes_count": c.get("votes", 0)}
        for c in (poll.get("choices") or [])
    ]
    return {
        "id": note_id,
        "expires_at": poll.get("expiresAt"),
        "expired": poll.get("expired", False),
        "multiple": poll.get("multiple", False),
        "votes_count": sum(o["votes_count"] for o in options),
        "voters_count": None,
        "voted": poll.get("voted", False),
        "own_votes": [],
        "options": options,
        "emojis": [],
    }
