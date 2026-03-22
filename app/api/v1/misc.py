from fastapi import APIRouter, Depends, HTTPException, Query

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


# ── Notifications ──────────────────────────────────────────────────────

@router.get("/notifications")
async def get_notifications(
    limit: int = Query(20, le=40),
    max_id: str = Query(None),
    since_id: str = Query(None),
    exclude_types: list[str] = Query(default=[]),
    mk: MastodonClient = Depends(_client),
):
    params = {"limit": limit}
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
    limit: int = Query(20, le=40),
    mk: MastodonClient = Depends(_client),
):
    params = {"limit": limit}
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


# ── Lists（アンテナ無効・ロール制限=0）────────────────────────────────

@router.get("/lists")
async def get_lists(mk: MastodonClient = Depends(_client)):
    return []


@router.post("/lists")
async def create_list():
    raise HTTPException(
        status_code=403,
        detail="List/antenna creation is disabled (role limit: 0)"
    )


@router.get("/lists/{list_id}")
async def get_list(list_id: str):
    raise HTTPException(status_code=404, detail="List not found")


@router.delete("/lists/{list_id}")
async def delete_list(list_id: str):
    raise HTTPException(status_code=404, detail="List not found")


@router.get("/lists/{list_id}/accounts")
async def list_accounts(list_id: str):
    return []


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
