from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user, get_mastodon_token
from app.core.config import settings
from app.db.models import User
from app.services.mastodon_client import MastodonClient

router = APIRouter(prefix="/api/v1", tags=["accounts"])


def _client(
    token: str = Depends(get_mastodon_token),
    current_user: User = Depends(get_current_user),
) -> MastodonClient:
    return MastodonClient(token, current_user.mastodon_instance)


@router.get("/accounts/verify_credentials")
async def verify_credentials(local_user: User = Depends(get_current_user)):
    """ローカルDBのユーザー情報を Mastodon Account 形式で返す。"""
    avatar = local_user.avatar_url or f"{settings.PROXY_BASE_URL or settings.MASTODON_INSTANCE_URL}/identicon/{local_user.id}"
    header = local_user.header_url or f"{settings.PROXY_BASE_URL or settings.MASTODON_INSTANCE_URL}/static-assets/transparent.png"
    return {
        "id": local_user.id,
        "username": local_user.username,
        "acct": local_user.username,
        "display_name": local_user.display_name or local_user.username,
        "locked": local_user.is_locked,
        "bot": local_user.is_bot,
        "created_at": local_user.created_at.isoformat(),
        "note": local_user.bio or "",
        "url": f"{settings.PROXY_BASE_URL or settings.MASTODON_INSTANCE_URL}/@{local_user.username}",
        "avatar": avatar,
        "avatar_static": avatar,
        "header": header,
        "header_static": header,
        "followers_count": 0,
        "following_count": 0,
        "statuses_count": 0,
        "last_status_at": None,
        "emojis": [],
        "fields": [],
        "source": {
            "privacy": "public",
            "sensitive": False,
            "language": "",
            "note": local_user.bio or "",
            "fields": [],
        },
        "pleroma": {"is_admin": False, "is_moderator": False},
    }


@router.patch("/accounts/update_credentials")
async def update_credentials(
    request_data: dict = {},
    mk: MastodonClient = Depends(_client),
):
    return await mk.update_credentials(**request_data)


@router.get("/accounts/search")
async def search_accounts(
    q: str = Query(...),
    limit: int = Query(40, le=80),
    mk: MastodonClient = Depends(_client),
):
    return await mk.search_accounts(q, limit=limit)


@router.get("/accounts/{account_id}")
async def get_account(account_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.get_account(account_id)


@router.get("/accounts/{account_id}/statuses")
async def account_statuses(
    account_id: str,
    limit: int = Query(20, le=40),
    max_id: str = Query(None),
    since_id: str = Query(None),
    mk: MastodonClient = Depends(_client),
):
    params = {"limit": limit}
    if max_id:
        params["max_id"] = max_id
    if since_id:
        params["since_id"] = since_id
    return await mk.get_account_statuses(account_id, **params)


@router.get("/accounts/{account_id}/followers")
async def account_followers(account_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.get_followers(account_id)


@router.get("/accounts/{account_id}/following")
async def account_following(account_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.get_following(account_id)


@router.post("/accounts/{account_id}/follow")
async def follow_account(account_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.follow(account_id)


@router.post("/accounts/{account_id}/unfollow")
async def unfollow_account(account_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.unfollow(account_id)


@router.post("/accounts/{account_id}/block")
async def block_account(account_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.block(account_id)


@router.post("/accounts/{account_id}/unblock")
async def unblock_account(account_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.unblock(account_id)


@router.post("/accounts/{account_id}/mute")
async def mute_account(account_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.mute(account_id)


@router.post("/accounts/{account_id}/unmute")
async def unmute_account(account_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.unmute(account_id)


@router.get("/blocks")
async def get_blocks(mk: MastodonClient = Depends(_client)):
    return await mk.get_blocks()


@router.get("/mutes")
async def get_mutes(mk: MastodonClient = Depends(_client)):
    return await mk.get_mutes()
