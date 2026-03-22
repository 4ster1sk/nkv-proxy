"""
Misskey /api/endpoints — 完全互換実装

レスポンス形式: 文字列の配列 (エンドポイント名一覧)
  POST /api/endpoints → ["admin/abuse-user-reports", "admin/accounts/create", ...]

エンドポイント一覧は Misskey ソースコード
  packages/backend/src/server/api/endpoints/
のディレクトリ構造に基づき、2026年3月時点の develop ブランチを参照して網羅。

上流 Misskey に転送すれば常に最新の一覧を得られるため、
転送に失敗した場合のみこのハードコードリストをフォールバックとして使う。
"""

from fastapi import APIRouter, Request
import httpx
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["misskey-endpoints"])

# ---------------------------------------------------------------------------
# Misskey エンドポイント完全一覧
# (packages/backend/src/server/api/endpoints/ ディレクトリ構造から生成)
# ---------------------------------------------------------------------------
MISSKEY_ENDPOINTS: list[str] = [
    # ── admin ───────────────────────────────────────────────────────────────
    "admin/abuse-user-reports",
    "admin/accounts/create",
    "admin/accounts/delete",
    "admin/accounts/find-by-email",
    "admin/ad/create",
    "admin/ad/delete",
    "admin/ad/list",
    "admin/ad/update",
    "admin/announcements/create",
    "admin/announcements/delete",
    "admin/announcements/list",
    "admin/announcements/update",
    "admin/avatar-decorations/create",
    "admin/avatar-decorations/delete",
    "admin/avatar-decorations/list",
    "admin/avatar-decorations/update",
    "admin/delete-account",
    "admin/delete-all-files-of-a-user",
    "admin/drive/clean-remote-files",
    "admin/drive/cleanup",
    "admin/drive/files",
    "admin/drive/show-file",
    "admin/emoji/add",
    "admin/emoji/add-aliases-bulk",
    "admin/emoji/copy",
    "admin/emoji/delete",
    "admin/emoji/delete-bulk",
    "admin/emoji/import-zip",
    "admin/emoji/list",
    "admin/emoji/list-remote",
    "admin/emoji/remove-aliases-bulk",
    "admin/emoji/set-aliases-bulk",
    "admin/emoji/set-category-bulk",
    "admin/emoji/set-license-bulk",
    "admin/emoji/update",
    "admin/federation/delete-all-files",
    "admin/federation/refresh-remote-instance-metadata",
    "admin/federation/remove-all-following",
    "admin/federation/update-instance",
    "admin/get-index-stats",
    "admin/get-table-stats",
    "admin/get-user-ips",
    "admin/invite/create",
    "admin/invite/list",
    "admin/meta",
    "admin/promo/create",
    "admin/queue/clear",
    "admin/queue/deliver-delayed",
    "admin/queue/inbox-delayed",
    "admin/queue/promote",
    "admin/queue/stats",
    "admin/relays/add",
    "admin/relays/list",
    "admin/relays/remove",
    "admin/reset-password",
    "admin/resolve-abuse-user-report",
    "admin/roles/assign",
    "admin/roles/create",
    "admin/roles/delete",
    "admin/roles/list",
    "admin/roles/show",
    "admin/roles/unassign",
    "admin/roles/update",
    "admin/roles/update-default-policies",
    "admin/roles/users",
    "admin/send-email",
    "admin/server-info",
    "admin/show-moderation-logs",
    "admin/show-user",
    "admin/show-users",
    "admin/suspend-user",
    "admin/unset-user-avatar",
    "admin/unset-user-banner",
    "admin/unsuspend-user",
    "admin/update-meta",
    "admin/update-user-note",
    # ── announcements ────────────────────────────────────────────────────────
    "announcements",
    # ── antenna ─────────────────────────────────────────────────────────────
    # (antennaLimit=0 のためエンドポイント自体は存在するが作成は 403)
    "antennas/create",
    "antennas/delete",
    "antennas/list",
    "antennas/notes",
    "antennas/show",
    "antennas/update",
    # ── ap ──────────────────────────────────────────────────────────────────
    "ap/get",
    "ap/show",
    # ── auth ────────────────────────────────────────────────────────────────
    "auth/accept",
    "auth/deny",
    "auth/session/generate",
    "auth/session/show",
    "auth/session/userkey",
    # ── blocking ────────────────────────────────────────────────────────────
    "blocking/create",
    "blocking/delete",
    "blocking/list",
    # ── channels ────────────────────────────────────────────────────────────
    "channels/create",
    "channels/favorite",
    "channels/featured",
    "channels/follow",
    "channels/followed",
    "channels/my-favorites",
    "channels/owned",
    "channels/search",
    "channels/show",
    "channels/timeline",
    "channels/unfavorite",
    "channels/unfollow",
    "channels/update",
    # ── clips ───────────────────────────────────────────────────────────────
    "clips/add-note",
    "clips/create",
    "clips/delete",
    "clips/favorite",
    "clips/list",
    "clips/my-favorites",
    "clips/notes",
    "clips/remove-note",
    "clips/show",
    "clips/unfavorite",
    "clips/update",
    # ── drive ───────────────────────────────────────────────────────────────
    "drive",
    "drive/files",
    "drive/files/attached-notes",
    "drive/files/check-existence",
    "drive/files/create",
    "drive/files/delete",
    "drive/files/find",
    "drive/files/show",
    "drive/files/update",
    "drive/files/upload-from-url",
    "drive/folders",
    "drive/folders/create",
    "drive/folders/delete",
    "drive/folders/find",
    "drive/folders/show",
    "drive/folders/update",
    "drive/stream",
    # ── email-address ───────────────────────────────────────────────────────
    "email-address/available",
    # ── emoji ───────────────────────────────────────────────────────────────
    "emoji",
    "emojis",
    # ── endpoint ────────────────────────────────────────────────────────────
    "endpoint",
    "endpoints",
    # ── federation ──────────────────────────────────────────────────────────
    "federation/followers",
    "federation/following",
    "federation/instances",
    "federation/show-instance",
    "federation/stats",
    "federation/update-remote-user",
    "federation/users",
    # ── flash ───────────────────────────────────────────────────────────────
    "flash/create",
    "flash/delete",
    "flash/featured",
    "flash/like",
    "flash/my",
    "flash/my-likes",
    "flash/show",
    "flash/unlike",
    "flash/update",
    # ── following ───────────────────────────────────────────────────────────
    "following/create",
    "following/delete",
    "following/invalidate",
    "following/requests/accept",
    "following/requests/cancel",
    "following/requests/list",
    "following/requests/reject",
    "following/update",
    # ── gallery ─────────────────────────────────────────────────────────────
    "gallery/featured",
    "gallery/liked",
    "gallery/my-liked-posts",
    "gallery/posts",
    "gallery/posts/create",
    "gallery/posts/delete",
    "gallery/posts/like",
    "gallery/posts/show",
    "gallery/posts/unlike",
    "gallery/posts/update",
    # ── get-online-users-count ───────────────────────────────────────────────
    "get-online-users-count",
    # ── hashtags ────────────────────────────────────────────────────────────
    "hashtags/list",
    "hashtags/search",
    "hashtags/show",
    "hashtags/trend",
    "hashtags/users",
    # ── i ───────────────────────────────────────────────────────────────────
    "i",
    "i/2fa/done",
    "i/2fa/key-done",
    "i/2fa/password-less",
    "i/2fa/register",
    "i/2fa/register-key",
    "i/2fa/remove",
    "i/2fa/remove-key",
    "i/2fa/update-key",
    "i/apps",
    "i/authorized-apps",
    "i/change-password",
    "i/claim-achievement",
    "i/delete-account",
    "i/export-antennas",
    "i/export-blocking",
    "i/export-clips",
    "i/export-favorites",
    "i/export-following",
    "i/export-muting",
    "i/export-notes",
    "i/export-user-lists",
    "i/favorites",
    "i/gallery/likes",
    "i/gallery/posts",
    "i/get-word-muted-notes-count",
    "i/import-antennas",
    "i/import-blocking",
    "i/import-following",
    "i/import-muting",
    "i/import-user-lists",
    "i/move",
    "i/notifications",
    "i/notifications-grouped",
    "i/page-likes",
    "i/pages",
    "i/pin",
    "i/read-all-unread-notes",
    "i/read-announcement",
    "i/regenerate-token",
    "i/registry/get",
    "i/registry/get-all",
    "i/registry/keys",
    "i/registry/keys-with-type",
    "i/registry/remove",
    "i/registry/scopes-with-domain",
    "i/registry/set",
    "i/revoke-all-tokens",
    "i/signin-history",
    "i/unpin",
    "i/update",
    "i/update-email",
    "i/webhooks/create",
    "i/webhooks/delete",
    "i/webhooks/list",
    "i/webhooks/show",
    "i/webhooks/update",
    # ── invite ──────────────────────────────────────────────────────────────
    "invite/create",
    "invite/delete",
    "invite/list",
    # ── meta ────────────────────────────────────────────────────────────────
    "meta",
    # ── miauth ──────────────────────────────────────────────────────────────
    "miauth/gen-token",
    # ── muting ──────────────────────────────────────────────────────────────
    "muting/create",
    "muting/delete",
    "muting/list",
    # ── my ──────────────────────────────────────────────────────────────────
    "my/apps",
    # ── notes ───────────────────────────────────────────────────────────────
    "notes",
    "notes/children",
    "notes/clips",
    "notes/conversation",
    "notes/create",
    "notes/delete",
    "notes/favorites/create",
    "notes/favorites/delete",
    "notes/featured",
    "notes/global-timeline",
    "notes/hybrid-timeline",
    "notes/local-timeline",
    "notes/mentions",
    "notes/polls/recommendation",
    "notes/polls/refresh",
    "notes/polls/vote",
    "notes/reactions",
    "notes/reactions/create",
    "notes/reactions/delete",
    "notes/recommended-timeline",
    "notes/renote-mute/create",
    "notes/renote-mute/delete",
    "notes/renote-mute/list",
    "notes/renotes",
    "notes/replies",
    "notes/scheduled",
    "notes/scheduled/create",
    "notes/scheduled/delete",
    "notes/scheduled/list",
    "notes/search",
    "notes/search-by-tag",
    "notes/show",
    "notes/state",
    "notes/thread-muting/create",
    "notes/thread-muting/delete",
    "notes/timeline",
    "notes/translate",
    "notes/unrenote",
    "notes/user-list-timeline",
    "notes/watching/create",
    "notes/watching/delete",
    # ── notifications ───────────────────────────────────────────────────────
    "notifications/create",
    "notifications/flush",
    "notifications/mark-all-as-read",
    "notifications/test-notification",
    # ── page-push ───────────────────────────────────────────────────────────
    "page-push",
    # ── pages ───────────────────────────────────────────────────────────────
    "pages/create",
    "pages/delete",
    "pages/featured",
    "pages/like",
    "pages/show",
    "pages/unlike",
    "pages/update",
    # ── ping ────────────────────────────────────────────────────────────────
    "ping",
    # ── pinned-users ────────────────────────────────────────────────────────
    "pinned-users",
    # ── promo ───────────────────────────────────────────────────────────────
    "promo/read",
    # ── reactions ───────────────────────────────────────────────────────────
    "reactions/delete",
    # ── relay ───────────────────────────────────────────────────────────────
    "relay/list",
    # ── roles ───────────────────────────────────────────────────────────────
    "roles/list",
    "roles/notes",
    "roles/show",
    "roles/users",
    # ── server-info ─────────────────────────────────────────────────────────
    "server-info",
    # ── signup ──────────────────────────────────────────────────────────────
    "signup",
    "signup-pending",
    # ── stats ───────────────────────────────────────────────────────────────
    "stats",
    # ── sw ──────────────────────────────────────────────────────────────────
    "sw/push",
    "sw/unregister",
    "sw/update-registration",
    # ── test ────────────────────────────────────────────────────────────────
    "test",
    # ── username ────────────────────────────────────────────────────────────
    "username/available",
    # ── users ───────────────────────────────────────────────────────────────
    "users",
    "users/clips",
    "users/featured-notes",
    "users/followers",
    "users/following",
    "users/gallery/posts",
    "users/get-frequently-replied-users",
    "users/lists/create",
    "users/lists/create-from-public",
    "users/lists/delete",
    "users/lists/favorite",
    "users/lists/get-memberships",
    "users/lists/list",
    "users/lists/member-notes",
    "users/lists/pull",
    "users/lists/push",
    "users/lists/show",
    "users/lists/unfavorite",
    "users/lists/update",
    "users/lists/update-membership",
    "users/notes",
    "users/pages",
    "users/reactions",
    "users/recommendation",
    "users/relation",
    "users/report-abuse",
    "users/search",
    "users/search-by-username-and-host",
    "users/show",
    "users/stats",
    "users/update-memo",
    # ── chat ────────────────────────────────────────────────────────────────
    "chat/history",
    "chat/messages/create",
    "chat/messages/delete",
    "chat/messages/read",
    "chat/rooms/create",
    "chat/rooms/delete",
    "chat/rooms/invitations/accept",
    "chat/rooms/invitations/cancel",
    "chat/rooms/invitations/create",
    "chat/rooms/invitations/decline",
    "chat/rooms/invitations/invited",
    "chat/rooms/invitations/sent",
    "chat/rooms/join",
    "chat/rooms/leave",
    "chat/rooms/members",
    "chat/rooms/messages",
    "chat/rooms/messages/delete",
    "chat/rooms/messages/react",
    "chat/rooms/messages/unreact",
    "chat/rooms/my",
    "chat/rooms/search",
    "chat/rooms/show",
    "chat/rooms/update",
]


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------

@router.post("/endpoint")
async def api_endpoint(request: Request):
    """
    特定エンドポイントの詳細情報を返す。
    上流に転送し、失敗時は空オブジェクトを返す。
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.MASTODON_INSTANCE_URL}/api/endpoint",
                json=body,
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {}


@router.post("/endpoints")
async def api_endpoints(request: Request):
    """
    利用可能な全エンドポイント名の配列を返す。
    まず上流 Misskey に転送を試み、失敗時はハードコードリストを返す。
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.MASTODON_INSTANCE_URL}/api/endpoints",
                json={},
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    return data
    except Exception:
        pass
    # フォールバック: ハードコードリスト（ソート済み）
    return sorted(MISSKEY_ENDPOINTS)
