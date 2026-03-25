"""
Mastodon → Misskey ユーザーオブジェクト変換

UserLite:    ノートの user フィールド等に埋め込む軽量版
UserDetailed: /api/i, /api/users/show 等の詳細版
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# HTML → プレーンテキスト変換
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str):
        self._parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p"):
            self._parts.append("\n")

    def get_text(self) -> str:
        text = "".join(self._parts)
        # 連続する改行を2つまでに圧縮
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    stripper = _HTMLStripper()
    try:
        stripper.feed(html)
        return stripper.get_text()
    except Exception:
        # フォールバック: タグを正規表現で除去
        return re.sub(r"<[^>]+>", "", html or "").strip()


# ---------------------------------------------------------------------------
# UserLite  — ノートの user フィールド等に埋め込む軽量版
# ---------------------------------------------------------------------------

def _extract_host(masto: dict) -> str | None:
    """
    Mastodon account オブジェクトからリモートホストを抽出する。
    acct フィールドが "user@host" 形式ならその host 部分を返す。
    ローカルユーザー ("user" のみ) は None を返す。
    """
    acct = masto.get("acct", "")
    if "@" in acct:
        return acct.split("@", 1)[1]
    return masto.get("domain") or None


def masto_to_misskey_user_lite(masto: dict) -> dict:
    """
    Mastodon account → Misskey UserLite

    Misskey クライアントがノートの `user` フィールドとして期待する最小セット。
    """
    host = _extract_host(masto)
    instance = (
        {
            "name": masto.get("server_name"),
            "softwareName": masto.get("server_software"),
            "softwareVersion": masto.get("server_software_version"),
        }
        if host
        else None
    )

    return {
        "id": masto.get("id", ""),
        "name": masto.get("display_name") or masto.get("username", ""),
        "username": masto.get("username", ""),
        "host": host,
        "avatarUrl": masto.get("avatar") or masto.get("avatar_static"),
        "avatarBlurhash": None,
        "avatarDecorations": [],
        "isBot": masto.get("bot", False),
        "isCat": masto.get("is_cat", False),
        "emojis": {},
        "onlineStatus": "unknown",
        "badgeRoles": [],
        "instance": instance,
    }


# ---------------------------------------------------------------------------
# UserDetailed — /api/i, /api/users/show 等の詳細版
# ---------------------------------------------------------------------------

def masto_to_misskey_user_detailed(
    masto: dict,
    db_user=None,       # app.db.models.User (任意)
    is_me: bool = False,
) -> dict:
    """
    Mastodon account → Misskey UserDetailed

    db_user が渡された場合はDB側の情報（totp 等）で補完する。
    is_me=True の場合は /api/i 用の自分自身フィールドも含める。
    """
    # UserLite ベースから構築
    base = masto_to_misskey_user_lite(masto)

    # description: Mastodon は HTML → プレーンテキストに変換
    description = html_to_text(masto.get("note", ""))

    # fields
    fields = [
        {"name": f.get("name", ""), "value": html_to_text(f.get("value", ""))}
        for f in (masto.get("fields") or [])
    ]

    # 2FA: DBユーザーから取得（なければ false）
    totp_enabled = bool(db_user.totp_enabled) if db_user else False
    totp_backup = "none" if not totp_enabled else "full"

    detailed = {
        **base,
        # プロフィール
        "url": masto.get("url"),
        "uri": masto.get("url"),
        "description": description,
        "location": None,
        "birthday": None,
        "lang": None,
        "fields": fields,
        "verifiedLinks": [
            f.get("value", "") for f in (masto.get("fields") or [])
            if f.get("verified_at")
        ],
        # バナー
        "bannerUrl": masto.get("header") or None,
        "bannerBlurhash": None,
        # ステータス
        "isLocked": masto.get("locked", False),
        "isSilenced": False,
        "isSuspended": False,
        "isAdmin": False,
        "isModerator": False,
        "isExplorable": True,
        "isDeleted": False,
        # カウンタ
        "followersCount": masto.get("followers_count", 0),
        "followingCount": masto.get("following_count", 0),
        "notesCount": masto.get("statuses_count", 0),
        # 日時
        "createdAt": masto.get("created_at", ""),
        "updatedAt": masto.get("created_at", ""),
        "lastFetchedAt": None,
        # ピン
        "pinnedNoteIds": [],
        "pinnedNotes": [],
        "pinnedPageId": None,
        "pinnedPage": None,
        # フォロー関係
        "movedTo": None,
        "alsoKnownAs": [],
        "followersVisibility": "public",
        "followingVisibility": "public",
        "publicReactions": True,
        "hasPendingFollowRequestFromYou": False,
        "hasPendingFollowRequestToYou": False,
        # セキュリティ
        "twoFactorEnabled": totp_enabled,
        "twoFactorBackupCodesStock": totp_backup,
        "usePasswordLessLogin": False,
        "securityKeys": False,
        "securityKeysList": [],
        # ロール
        "roles": [],
        "badgeRoles": [],
        # チャット
        "chatScope": "none",
        "canChat": False,
        # ミュート
        "mutedWords": [],
        "hardMutedWords": [],
        "mutedInstances": [],
        "mutingNotificationTypes": [],
    }

    # /api/i (自分自身) 専用フィールド
    if is_me:
        detailed.update({
            # 通知・未読フラグ
            "hasUnreadSpecifiedNotes": False,
            "hasUnreadMentions": False,
            "hasUnreadChatMessages": False,
            "hasUnreadAnnouncement": False,
            "unreadAnnouncements": [],
            "hasUnreadAntenna": False,
            "hasUnreadChannel": False,
            "hasUnreadNotification": False,
            "hasPendingReceivedFollowRequest": False,
            "unreadNotificationsCount": 0,
            # 設定
            "autoAcceptFollowed": False,
            "alwaysMarkNsfw": False,
            "autoSensitive": False,
            "carefulBot": False,
            "noCrawle": False,
            "preventAiLearning": False,
            "hideOnlineStatus": False,
            "injectFeaturedNote": False,
            "receiveAnnouncementEmail": False,
            "followedMessage": None,
            # バッジ
            "achievements": [],
            "loggedInDays": 0,
            # メール（非公開）
            "email": None,
            "emailVerified": False,
            # アバター・バナーID
            "avatarId": None,
            "bannerId": None,
            # 通知設定
            "emailNotificationTypes": [],
            "notificationRecieveConfig": {},
            # ポリシー
            "policies": _default_policies(),
        })

    return detailed


def _default_policies() -> dict:
    """Misskey の policies フィールドのデフォルト値。"""
    return {
        "gtlAvailable": True,
        "ltlAvailable": True,
        "canPublicNote": True,
        "mentionLimit": 20,
        "canInvite": False,
        "inviteLimit": 0,
        "inviteLimitCycle": 10080,
        "inviteExpirationTime": 0,
        "canManageCustomEmojis": False,
        "canManageAvatarDecorations": False,
        "canSearchNotes": True,
        "canSearchUsers": True,
        "canUseTranslator": False,
        "canHideAds": False,
        "driveCapacityMb": 1024,
        "maxFileSizeMb": 100,
        "alwaysMarkNsfw": False,
        "canUpdateBioMedia": True,
        "pinLimit": 5,
        "antennaLimit": 0,
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
        "chatAvailability": "unavailable",
        "noteDraftLimit": 10,
        "scheduledNoteLimit": 10,
        "watermarkAvailable": False,
        "uploadableFileTypes": [
            "image/*", "video/*", "audio/*", "text/plain",
        ],
    }
