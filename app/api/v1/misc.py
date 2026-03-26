from fastapi import APIRouter, Depends, Query, Request

from app.core.auth import get_current_user, get_mastodon_token
from app.core.config import settings
from app.db.models import User
from app.services.mastodon_client import MastodonClient

router = APIRouter(prefix="/api/v1", tags=["misc"])


def _client(
    token: str = Depends(get_mastodon_token),
    current_user: User = Depends(get_current_user),
) -> MastodonClient:
    return MastodonClient(token, current_user.mastodon_instance)


def _clamp(limit: int, user_max: int | None) -> int:
    """limit をユーザー設定上限（未設定時はグローバルデフォルト）でクランプする。"""
    return min(limit, user_max or settings.API_LIMIT_MAX)


# ── Notifications ──────────────────────────────────────────────────────

@router.get("/notifications")
async def get_notifications(
    limit: int = Query(20, ge=1),
    max_id: str = Query(None),
    since_id: str = Query(None),
    exclude_types: list[str] = Query(default=[]),
    current_user: User = Depends(get_current_user),
    mk: MastodonClient = Depends(_client),
):
    params = {"limit": _clamp(limit, current_user.limit_max_notifications)}
    if max_id:
        params["max_id"] = max_id
    if since_id:
        params["since_id"] = since_id
    return await mk.get_notifications(**params)


@router.delete("/notifications")
async def clear_notifications(mk: MastodonClient = Depends(_client)):
    return await mk.clear_notifications()


@router.get("/notifications/{notification_id}")
async def get_notification(notification_id: str, mk: MastodonClient = Depends(_client)):
    return {}


@router.post("/notifications/{notification_id}/dismiss")
async def dismiss_notification(notification_id: str, mk: MastodonClient = Depends(_client)):
    return {}


# ── Search ─────────────────────────────────────────────────────────────

@router.get("/search")
async def search(
    q: str = Query(...),
    type: str = Query(None),
    limit: int = Query(20, ge=1),
    mk: MastodonClient = Depends(_client),
):
    params = {"limit": min(limit, settings.API_LIMIT_MAX)}
    if type:
        params["type"] = type
    return await mk.search(q, **params)


# ── Instance ───────────────────────────────────────────────────────────

@router.get("/instance")
async def get_instance(mk: MastodonClient = Depends(_client)):
    try:
        return await mk.get_instance()
    except Exception:
        return {
            "uri": (settings.PROXY_BASE_URL or settings.MASTODON_INSTANCE_URL).replace("https://", "").rstrip("/"),
            "title": settings.INSTANCE_TITLE,
            "description": settings.INSTANCE_DESCRIPTION,
            "version": settings.INSTANCE_VERSION,
            "stats": {"user_count": 0, "status_count": 0, "domain_count": 1},
            "languages": ["ja", "en"],
            "contact_account": None,
            "rules": [],
        }


@router.get("/instance/peers")
async def instance_peers():
    return []


@router.get("/instance/activity")
async def instance_activity():
    return []


# ── Custom emojis ──────────────────────────────────────────────────────

@router.get("/custom_emojis")
async def custom_emojis(mk: MastodonClient = Depends(_client)):
    try:
        return await mk.get_custom_emojis()
    except Exception:
        return []


# ── Lists ──────────────────────────────────────────────────────────────

@router.get("/lists")
async def get_lists(mk: MastodonClient = Depends(_client)):
    return await mk.get_lists()


@router.post("/lists")
async def create_list(request: Request, mk: MastodonClient = Depends(_client)):
    body = await request.json()
    return await mk.create_list(body.get("title", ""))


@router.get("/lists/{list_id}")
async def get_list(list_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.get_list(list_id)


@router.put("/lists/{list_id}")
async def update_list(list_id: str, request: Request, mk: MastodonClient = Depends(_client)):
    body = await request.json()
    return await mk.update_list(list_id, body.get("title", ""))


@router.delete("/lists/{list_id}")
async def delete_list(list_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.delete_list(list_id)


@router.get("/lists/{list_id}/accounts")
async def list_accounts(
    list_id: str,
    limit: int = Query(40, ge=1),
    mk: MastodonClient = Depends(_client),
):
    return await mk.get_list_accounts(list_id, limit=min(limit, 80))


@router.post("/lists/{list_id}/accounts")
async def add_list_accounts(list_id: str, request: Request, mk: MastodonClient = Depends(_client)):
    body = await request.json()
    return await mk.add_list_accounts(list_id, body.get("account_ids", []))


@router.delete("/lists/{list_id}/accounts")
async def remove_list_accounts(list_id: str, request: Request, mk: MastodonClient = Depends(_client)):
    body = await request.json()
    return await mk.remove_list_accounts(list_id, body.get("account_ids", []))


@router.get("/timelines/list/{list_id}")
async def list_timeline(
    list_id: str,
    limit: int = Query(20, ge=1),
    max_id: str = Query(None),
    since_id: str = Query(None),
    min_id: str = Query(None),
    current_user: User = Depends(get_current_user),
    mk: MastodonClient = Depends(_client),
):
    return await mk.list_timeline(
        list_id,
        limit=_clamp(limit, current_user.limit_max_tl),
        max_id=max_id,
        since_id=since_id,
        min_id=min_id,
    )


# ── Misc ───────────────────────────────────────────────────────────────

@router.get("/filters")
async def get_filters(mk: MastodonClient = Depends(_client)):
    return []


@router.get("/followed_tags")
async def get_followed_tags(mk: MastodonClient = Depends(_client)):
    return []


@router.get("/preferences")
async def get_preferences(mk: MastodonClient = Depends(_client)):
    return {
        "posting:default:visibility": "public",
        "posting:default:sensitive": False,
        "posting:default:language": None,
        "reading:expand:media": "default",
        "reading:expand:spoilers": False,
    }
