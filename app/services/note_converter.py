"""
Mastodon ステータス → Misskey ノート変換

Mastodon の status オブジェクトを Misskey の Note 形式に変換する。
"""
from __future__ import annotations

from app.services.user_converter import html_to_text, masto_to_misskey_user_lite


def _build_reaction_key(er: dict) -> tuple[str, str | None]:
    """
    Fedibird emoji_reaction エントリから Misskey 形式のリアクションキーと画像URLを構築。

    Returns (reaction_key, emoji_url).
      - Unicode:        "❤"
      - Local custom:   ":awesome:"
      - Remote custom:  ":awesome@remote.host:"
    """
    name = er.get("name", "")
    domain = er.get("domain")
    url = er.get("url")

    if not name:
        return ("", None)

    # 既に :...: 形式（Nekonoverse スタイル）
    if name.startswith(":") and name.endswith(":"):
        return (name, url)

    # 非ASCII文字 = Unicode 絵文字
    if not name.isascii():
        return (name, None)

    # ASCII shortcode（コロンなし）
    if domain:
        return (f":{name}@{domain}:", url)
    return (f":{name}:", url)


def masto_status_to_mk_note(status: dict) -> dict:
    """
    Mastodon status → Misskey Note

    Misskey クライアントが期待する Note フォーマットで返す。
    """
    if not status:
        return {}

    account = status.get("account") or {}
    user_lite = masto_to_misskey_user_lite(account)

    # CW → cw フィールド
    cw = status.get("spoiler_text") or None

    # content: HTML → プレーンテキスト
    text = html_to_text(status.get("content", ""))

    # visibility マッピング
    vis_map = {
        "public": "public",
        "unlisted": "home",
        "private": "followers",
        "direct": "specified",
    }
    visibility = vis_map.get(status.get("visibility", "public"), "public")

    # 添付ファイル変換
    files = []
    for att in (status.get("media_attachments") or []):
        att_type = att.get("type", "unknown")
        mime_map = {
            "image": "image/jpeg",
            "video": "video/mp4",
            "gifv": "video/mp4",
            "audio": "audio/mpeg",
            "unknown": "application/octet-stream",
        }
        files.append({
            "id": att.get("id", ""),
            "createdAt": status.get("created_at", ""),
            "name": att.get("description") or att.get("id", ""),
            "type": mime_map.get(att_type, "application/octet-stream"),
            "md5": "",
            "size": 0,
            "isSensitive": status.get("sensitive", False),
            "blurhash": att.get("blurhash"),
            "properties": {},
            "url": att.get("url") or att.get("remote_url", ""),
            "thumbnailUrl": att.get("preview_url"),
            "comment": att.get("description"),
            "folderId": None,
            "folder": None,
            "userId": account.get("id"),
            "user": None,
        })

    # リアクション: emoji_reactions (Fedibird拡張) を優先、なければ favourites_count
    reactions: dict = {}
    reaction_emojis: dict = {}
    my_reaction: str | None = None
    fedibird_reactions = status.get("emoji_reactions") or []
    if fedibird_reactions:
        for er in fedibird_reactions:
            rkey, emoji_url = _build_reaction_key(er)
            if not rkey:
                continue
            reactions[rkey] = er.get("count", 0)
            if emoji_url:
                # Misskey の reactionEmojis はコロンなしキー (e.g. "blobcat@remote")
                reaction_emojis[rkey.strip(":")] = emoji_url
            if er.get("me"):
                my_reaction = rkey
    elif status.get("favourites_count", 0) > 0:
        reactions["❤"] = status["favourites_count"]
    if status.get("favourited") and not my_reaction:
        my_reaction = "❤"

    # リノート (reblog)
    renote = None
    renote_id = None
    if status.get("reblog"):
        renote = masto_status_to_mk_note(status["reblog"])
        renote_id = status["reblog"].get("id")

    # 返信
    reply_id = status.get("in_reply_to_id")

    # polls → poll
    poll = None
    if status.get("poll"):
        p = status["poll"]
        poll = {
            "id": p.get("id", ""),
            "expiresAt": p.get("expires_at"),
            "multiple": p.get("multiple", False),
            "choices": [
                {
                    "text": c.get("title", ""),
                    "votes": c.get("votes_count", 0),
                    "isVoted": c.get("voted", False),
                }
                for c in (p.get("options") or [])
            ],
            "votes": sum(c.get("votes_count", 0) for c in (p.get("options") or [])),
            "voted": p.get("voted", False),
            "ownVoteIds": [],
        }

    # mentions
    mentions = [
        m.get("id", "")
        for m in (status.get("mentions") or [])
    ]

    # tags
    tags = [t.get("name", "") for t in (status.get("tags") or [])]

    return {
        "id": status.get("id", ""),
        "createdAt": status.get("created_at", ""),
        "userId": account.get("id", ""),
        "user": user_lite,
        "text": text or None,
        "cw": cw,
        "visibility": visibility,
        "localOnly": False,
        "reactionAcceptance": None,
        "renoteCount": status.get("reblogs_count", 0),
        "repliesCount": status.get("replies_count", 0),
        "reactionCount": sum(reactions.values()),
        "reactions": reactions,
        "reactionEmojis": reaction_emojis,
        "fileIds": [f["id"] for f in files],
        "files": files,
        "replyId": reply_id,
        "renoteId": renote_id,
        "renote": renote,
        "clippedCount": 0,
        "mentions": mentions,
        "tags": tags,
        "emojis": reaction_emojis,
        "poll": poll,
        # Mastodon 側の追加情報
        "uri": status.get("uri"),
        "url": status.get("url"),
        "myReaction": my_reaction,
        "favourited": status.get("favourited", False),
        "reblogged": status.get("reblogged", False),
        "bookmarked": status.get("bookmarked", False),
    }


def masto_statuses_to_mk_notes(statuses: list) -> list:
    return [masto_status_to_mk_note(s) for s in (statuses or [])]


# ---------------------------------------------------------------------------
# Notification conversion: Mastodon → Misskey
# ---------------------------------------------------------------------------

_MASTO_TO_MK_TYPE: dict[str, str | None] = {
    "mention":              None,   # determined by in_reply_to_id (see below)
    "reblog":               "renote",
    "favourite":            "reaction",
    "emoji_reaction":       "reaction",   # Fedibird extension
    "follow":               "follow",
    "follow_request":       "receiveFollowRequest",
    "poll":                 "pollEnded",
    "status":               None,   # new post from followed — no Misskey equivalent
    "update":               None,   # status edit — no Misskey notification equivalent
    "admin.sign_up":        None,
    "admin.report":         None,
}


def masto_notification_to_mk(notif: dict) -> dict | None:
    """
    Mastodon notification → Misskey notification 形式に変換する。

    未対応の type は None を返す（呼び出し元でフィルタリングする）。
    """
    masto_type = notif.get("type", "")
    status = notif.get("status")

    if masto_type == "mention":
        # status に in_reply_to_id があれば reply、なければ mention
        mk_type: str | None = "reply" if (status and status.get("in_reply_to_id")) else "mention"
    else:
        mk_type = _MASTO_TO_MK_TYPE.get(masto_type)
        if mk_type is None:
            return None

    account = notif.get("account") or {}
    user = masto_to_misskey_user_lite(account)

    result: dict = {
        "id": notif.get("id", ""),
        "createdAt": notif.get("created_at", ""),
        "isRead": False,
        "type": mk_type,
        "userId": account.get("id", ""),
        "user": user,
    }

    if status:
        result["note"] = masto_status_to_mk_note(status)

    # reaction type には reaction フィールドが必要
    if mk_type == "reaction":
        # Fedibird emoji_reaction は emoji フィールドにショートコードが入る
        result["reaction"] = notif.get("emoji") or "❤"

    return result


def mk_renote_stub(account: dict, original_note_id: str) -> dict:
    """
    `reblogged_by` で返ってきた Mastodon アカウントから
    Misskey 互換の Renote スタブオブジェクトを生成する。

    Mastodon の reblogged_by はアカウント一覧しか返さないため、
    元ノートへの参照 (renoteId) だけを持つ最小限のノートを構築する。
    id は (account_id, original_note_id) のペアから UUIDv5 で決定論的に生成。
    """
    import uuid as _uuid
    rel_id = str(_uuid.uuid5(
        _uuid.NAMESPACE_URL,
        f"renote:{account.get('id', '')}:{original_note_id}",
    ))
    return {
        "id": rel_id,
        "createdAt": account.get("created_at", ""),
        "userId": account.get("id", ""),
        "user": masto_to_misskey_user_lite(account),
        "text": None,
        "cw": None,
        "visibility": "followers",
        "localOnly": False,
        "reactionAcceptance": None,
        "renoteCount": 0,
        "repliesCount": 0,
        "reactionCount": 0,
        "reactions": {},
        "reactionEmojis": {},
        "fileIds": [],
        "files": [],
        "replyId": None,
        "renoteId": original_note_id,
        "renote": None,
        "clippedCount": 0,
        "tags": [],
        "emojis": [],
        "poll": None,
        "myReaction": None,
        "favourited": False,
        "reblogged": True,
        "bookmarked": False,
    }
