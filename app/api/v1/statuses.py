from fastapi import APIRouter, Depends, Query, Request

from app.core.auth import get_current_user, get_mastodon_token
from app.db.models import User
from app.services.mastodon_client import MastodonClient

router = APIRouter(prefix="/api/v1", tags=["statuses"])


def _client(
    token: str = Depends(get_mastodon_token),
    current_user: User = Depends(get_current_user),
) -> MastodonClient:
    return MastodonClient(token, current_user.mastodon_instance)


# ── Timelines ──────────────────────────────────────────────────────────

@router.get("/timelines/home")
async def home_timeline(
    limit: int = Query(20, le=40),
    max_id: str = Query(None),
    since_id: str = Query(None),
    until_id: str = Query(None),
    min_id: str = Query(None),
    mk: MastodonClient = Depends(_client),
):
    params: dict = {"limit": limit}
    # until_id → max_id (Mastodon), since_id → min_id (Mastodon)
    if until_id:
        params["max_id"] = until_id
    elif max_id:
        params["max_id"] = max_id
    if since_id:
        params["min_id"] = since_id
    elif min_id:
        params["min_id"] = min_id
    return await mk.home_timeline(**params)


@router.get("/timelines/public")
async def public_timeline(
    local: bool = Query(False),
    remote: bool = Query(False),
    limit: int = Query(20, le=40),
    max_id: str = Query(None),
    since_id: str = Query(None),
    until_id: str = Query(None),
    min_id: str = Query(None),
    mk: MastodonClient = Depends(_client),
):
    params: dict = {"limit": limit, "local": local, "remote": remote}
    if until_id:
        params["max_id"] = until_id
    elif max_id:
        params["max_id"] = max_id
    if since_id:
        params["min_id"] = since_id
    elif min_id:
        params["min_id"] = min_id
    return await mk.public_timeline(**params)


@router.get("/timelines/list/{list_id}")
async def list_timeline(list_id: str, mk: MastodonClient = Depends(_client)):
    return []


# ── Statuses ───────────────────────────────────────────────────────────

@router.post("/statuses")
async def create_status(request: Request, mk: MastodonClient = Depends(_client)):
    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        body = await request.json()
    else:
        form = await request.form()
        body = dict(form)
    return await mk.create_status(**body)


@router.get("/statuses/{status_id}")
async def get_status(status_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.get_status(status_id)


@router.delete("/statuses/{status_id}")
async def delete_status(status_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.delete_status(status_id)


@router.get("/statuses/{status_id}/context")
async def status_context(status_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.get_context(status_id)


@router.get("/statuses/{status_id}/reblogged_by")
async def reblogged_by(status_id: str, mk: MastodonClient = Depends(_client)):
    return []


@router.get("/statuses/{status_id}/favourited_by")
async def favourited_by(status_id: str, mk: MastodonClient = Depends(_client)):
    return []


@router.post("/statuses/{status_id}/favourite")
async def favourite_status(status_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.favourite(status_id)


@router.post("/statuses/{status_id}/unfavourite")
async def unfavourite_status(status_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.unfavourite(status_id)


@router.put("/statuses/{status_id}/emoji_reactions/{emoji}")
async def add_emoji_reaction(
    status_id: str, emoji: str, mk: MastodonClient = Depends(_client)
):
    return await mk.add_emoji_reaction(status_id, emoji)


@router.delete("/statuses/{status_id}/emoji_reactions/{emoji}")
async def remove_emoji_reaction(
    status_id: str, emoji: str, mk: MastodonClient = Depends(_client)
):
    return await mk.remove_emoji_reaction(status_id, emoji)


@router.get("/statuses/{status_id}/emoji_reactions")
async def get_emoji_reactions(status_id: str, mk: MastodonClient = Depends(_client)):
    return []


@router.post("/statuses/{status_id}/reblog")
async def reblog_status(status_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.reblog(status_id)


@router.post("/statuses/{status_id}/unreblog")
async def unreblog_status(status_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.unreblog(status_id)


@router.post("/statuses/{status_id}/bookmark")
async def bookmark_status(status_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.bookmark(status_id)


@router.post("/statuses/{status_id}/unbookmark")
async def unbookmark_status(status_id: str, mk: MastodonClient = Depends(_client)):
    return await mk.unbookmark(status_id)


@router.get("/bookmarks")
async def get_bookmarks(
    limit: int = Query(20, le=40), mk: MastodonClient = Depends(_client)
):
    return await mk.get_bookmarks(limit=limit)


@router.get("/favourites")
async def get_favourites(
    limit: int = Query(20, le=40), mk: MastodonClient = Depends(_client)
):
    return await mk.get_favourites(limit=limit)
