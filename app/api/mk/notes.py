"""
/api/notes/*, /api/users/lists/*, /api/notes/user-list-timeline
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.mk.helpers import (
    _body,
    _mastodon_client,
    _mastodon_client_with_user,
    _token,
)
from app.core.config import settings
from app.core.limit_utils import clamp_other, clamp_tl
from app.db import crud
from app.db.database import get_db
from app.services.instance_cache import supports_local_timeline
from app.services.note_converter import (
    _build_reaction_key,
    masto_status_to_mk_note,
    masto_statuses_to_mk_notes,
    mk_renote_stub,
)
from app.services.user_converter import (
    masto_to_misskey_user_detailed,
    masto_to_misskey_user_lite,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Timelines
# ---------------------------------------------------------------------------

@router.post("/notes/timeline")
async def api_notes_timeline(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk, db_user = await _mastodon_client_with_user(token, db)
    _tl_params: dict = {"limit": clamp_tl(body.get("limit", 20), db_user)}
    if body.get("untilId"):
        _tl_params["max_id"] = body["untilId"]
    if body.get("sinceId"):
        _tl_params["min_id"] = body["sinceId"]
    statuses = await mk.home_timeline(**_tl_params)
    return masto_statuses_to_mk_notes(statuses)


@router.post("/notes/local-timeline")
async def api_notes_local_timeline(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)

    ltl_setting = settings.ENABLE_LOCAL_TIMELINE.lower()

    if ltl_setting == "false":
        raise HTTPException(status_code=400, detail={
            "error": {
                "message": "Local timeline has been disabled.",
                "code": "LTL_DISABLED",
                "id": "45a6eb02-7695-4393-b023-dd3be9aaaefd",
                "kind": "client",
            }
        })
    elif ltl_setting == "auto":
        if token:
            result = await crud.get_token_with_user(db, token)
            if not result:
                result = await crud.get_api_key_by_key(db, token)
                if result:
                    from sqlalchemy import select as _sel

                    from app.db.models import User as _User
                    user_result = await db.execute(_sel(_User).where(_User.id == result.user_id))
                    user = user_result.scalar_one_or_none()
                else:
                    user = None
            else:
                _, user = result
            instance = (user.mastodon_instance if user else None) or settings.MASTODON_INSTANCE_URL
        else:
            instance = settings.MASTODON_INSTANCE_URL

        ltl_ok = await supports_local_timeline(instance)
        if not ltl_ok:
            raise HTTPException(status_code=400, detail={
                "error": {
                    "message": "Local timeline is not available on this instance.",
                    "code": "LTL_DISABLED",
                    "id": "45a6eb02-7695-4393-b023-dd3be9aaaefd",
                    "kind": "client",
                }
            })

    if not token:
        return []
    mk, db_user = await _mastodon_client_with_user(token, db)
    _tl_params: dict = {"local": True, "limit": clamp_tl(body.get("limit", 20), db_user)}
    if body.get("untilId"):
        _tl_params["max_id"] = body["untilId"]
    if body.get("sinceId"):
        _tl_params["min_id"] = body["sinceId"]
    statuses = await mk.public_timeline(**_tl_params)
    return masto_statuses_to_mk_notes(statuses)


@router.post("/notes/global-timeline")
async def api_notes_global_timeline(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        return []
    mk, db_user = await _mastodon_client_with_user(token, db)
    _tl_params: dict = {"limit": clamp_tl(body.get("limit", 20), db_user)}
    if body.get("untilId"):
        _tl_params["max_id"] = body["untilId"]
    if body.get("sinceId"):
        _tl_params["min_id"] = body["sinceId"]
    statuses = await mk.public_timeline(**_tl_params)
    return masto_statuses_to_mk_notes(statuses)


# ---------------------------------------------------------------------------
# Note CRUD
# ---------------------------------------------------------------------------

@router.post("/notes/create")
async def api_notes_create(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    vis = {"public": "public", "home": "unlisted", "followers": "private", "specified": "direct"}.get(
        body.get("visibility", "public"), "public"
    )
    status = await mk.create_status(
        status=body.get("text", ""),
        spoiler_text=body.get("cw"),
        visibility=vis,
        in_reply_to_id=body.get("replyId"),
        media_ids=body.get("fileIds"),
        poll=body.get("poll"),
    )
    return {"createdNote": masto_status_to_mk_note(status)}


@router.post("/notes/delete")
async def api_notes_delete(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    await mk.delete_status(body["noteId"])
    return {}


@router.post("/notes/show")
async def api_notes_show(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    status = await mk.get_status(body["noteId"])
    return masto_status_to_mk_note(status)


@router.post("/notes/state")
async def api_notes_state(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    note_id = body.get("noteId")
    if not note_id:
        raise HTTPException(status_code=400, detail="noteId is required")
    mk = await _mastodon_client(token, db)
    status = await mk.get_status(note_id)
    return {
        "isFavorited": bool(status.get("bookmarked")),
        "isMutedThread": bool(status.get("muted")),
        "isWatching": False,
    }


@router.post("/notes/renotes")
async def api_notes_renotes(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    note_id = body["noteId"]
    accounts = await mk.get_reblogged_by(note_id)
    return [mk_renote_stub(a, note_id) for a in accounts]


@router.post("/notes/replies")
async def api_notes_replies(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    context = await mk.get_context(body["noteId"])
    return masto_statuses_to_mk_notes(context.get("descendants", []))


@router.post("/notes/search")
async def api_notes_search(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk, db_user = await _mastodon_client_with_user(token, db)
    query = body.get("query", "")
    result = await mk.search(query, type="statuses", limit=clamp_other(body.get("limit", 20), db_user))
    statuses = result.get("statuses", []) if isinstance(result, dict) else []
    return masto_statuses_to_mk_notes(statuses)


# ---------------------------------------------------------------------------
# Reactions
# ---------------------------------------------------------------------------

@router.post("/notes/reactions/create")
async def api_reactions_create(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    reaction = body.get("reaction", "❤")
    try:
        status = await mk.add_emoji_reaction(body["noteId"], reaction)
    except Exception:
        status = await mk.favourite(body["noteId"])
    return masto_status_to_mk_note(status)


@router.post("/notes/reactions/delete")
async def api_reactions_delete(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    reaction = body.get("reaction", "❤")
    try:
        status = await mk.remove_emoji_reaction(body["noteId"], reaction)
    except Exception:
        status = await mk.unfavourite(body["noteId"])
    return masto_status_to_mk_note(status)


@router.post("/notes/reactions")
async def api_reactions_list(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    note_id = body.get("noteId", "")
    reaction = body.get("reaction")

    def _parse_reacted_by(entries: list, fallback_reaction: str) -> list:
        result = []
        for entry in entries:
            if "actor" in entry:
                account = entry["actor"]
                reaction = entry.get("emoji") or fallback_reaction
            else:
                account = entry
                reaction = fallback_reaction

            account = masto_to_misskey_user_lite(account)
            result.append(
                {
                    "id": account.get("id", ""),
                    "createdAt": account.get(
                        "created_at",
                        datetime.now(timezone.utc)
                        .isoformat(timespec="milliseconds")
                        .replace("+00:00", "Z"),
                    ),
                    "type": reaction,
                    "user": account,
                }
            )
        return result

    if reaction:
        try:
            entries = await mk.get_reacted_by(note_id, reaction)
            return _parse_reacted_by(
                entries if isinstance(entries, list) else [], reaction
            )
        except Exception:
            accounts = await mk._get(f"statuses/{note_id}/favourited_by")
            return [
                {
                    "id": a.get("id"),
                    "createdAt": a.get(
                        "created_at",
                        datetime.now(timezone.utc)
                        .isoformat(timespec="milliseconds")
                        .replace("+00:00", "Z"),
                    ),
                    "reaction": reaction,
                    "user": masto_to_misskey_user_lite(a),
                }
                for a in (accounts if isinstance(accounts, list) else [])
            ]

    status = await mk.get_status(note_id)
    fedibird_reactions = status.get("emoji_reactions") or []
    if fedibird_reactions:
        result = []
        for er in fedibird_reactions:
            rkey, _ = _build_reaction_key(er)
            if not rkey:
                continue
            if er.get("account_ids"):
                for aid in er["account_ids"]:
                    result.append({"id": aid, "createdAt": "", "reaction": rkey, "user": {"id": aid}})
            else:
                try:
                    entries = await mk.get_reacted_by(note_id, rkey)
                    result.extend(_parse_reacted_by(
                        entries if isinstance(entries, list) else [], rkey
                    ))
                except Exception:
                    for _ in range(er.get("count", 0)):
                        result.append({"id": "", "createdAt": "", "reaction": rkey, "user": {}})
        return result

    accounts = await mk._get(f"statuses/{note_id}/favourited_by")
    return [
        {"id": a.get("id"), "reaction": "❤", "user": masto_to_misskey_user_lite(a)}
        for a in (accounts if isinstance(accounts, list) else [])
    ]


@router.post("/notes/favorites/create")
async def api_favorites_create(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    status = await mk.bookmark(body["noteId"])
    return masto_status_to_mk_note(status)


@router.post("/notes/favorites/delete")
async def api_favorites_delete(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    status = await mk.unbookmark(body["noteId"])
    return masto_status_to_mk_note(status)


# ---------------------------------------------------------------------------
# User Lists & List Timeline
# ---------------------------------------------------------------------------

def _masto_list_to_mk(masto: dict) -> dict:
    """Mastodon list オブジェクト → Misskey UserList"""
    return {
        "id": masto.get("id", ""),
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "name": masto.get("title", ""),
        "userIds": [],
        "isPublic": False,
    }


@router.post("/users/lists/list")
async def api_users_lists_list(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    lists = await mk.get_lists()
    return [_masto_list_to_mk(lst) for lst in lists]


@router.post("/users/lists/show")
async def api_users_lists_show(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    list_id = body.get("listId")
    if not list_id:
        raise HTTPException(status_code=400, detail="listId is required")
    mk = await _mastodon_client(token, db)
    lst = await mk.get_list(list_id)
    return _masto_list_to_mk(lst)


@router.post("/users/lists/create")
async def api_users_lists_create(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    lst = await mk.create_list(body.get("name", ""))
    return _masto_list_to_mk(lst)


@router.post("/users/lists/update")
async def api_users_lists_update(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    list_id = body.get("listId")
    if not list_id:
        raise HTTPException(status_code=400, detail="listId is required")
    mk = await _mastodon_client(token, db)
    lst = await mk.update_list(list_id, body.get("name", ""))
    return _masto_list_to_mk(lst)


@router.post("/users/lists/delete")
async def api_users_lists_delete(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    list_id = body.get("listId")
    if not list_id:
        raise HTTPException(status_code=400, detail="listId is required")
    mk = await _mastodon_client(token, db)
    await mk.delete_list(list_id)
    return {}


@router.post("/users/lists/push")
async def api_users_lists_push(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    list_id = body.get("listId")
    if not list_id:
        raise HTTPException(status_code=400, detail="listId is required")
    mk = await _mastodon_client(token, db)
    await mk.add_list_accounts(list_id, [body["userId"]])
    return {}


@router.post("/users/lists/pull")
async def api_users_lists_pull(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    list_id = body.get("listId")
    if not list_id:
        raise HTTPException(status_code=400, detail="listId is required")
    mk = await _mastodon_client(token, db)
    await mk.remove_list_accounts(list_id, [body["userId"]])
    return {}


@router.post("/users/lists/get-memberships")
async def api_users_lists_get_memberships(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    list_id = body.get("listId")
    if not list_id:
        raise HTTPException(status_code=400, detail="listId is required")
    mk, db_user = await _mastodon_client_with_user(token, db)
    accounts = await mk.get_list_accounts(list_id, limit=clamp_other(body.get("limit", 30), db_user))
    return [masto_to_misskey_user_detailed(a) for a in accounts]


@router.post("/notes/user-list-timeline")
async def api_notes_user_list_timeline(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    list_id = body.get("listId")
    if not list_id:
        raise HTTPException(status_code=400, detail="listId is required")
    mk, db_user = await _mastodon_client_with_user(token, db)
    statuses = await mk.list_timeline(
        list_id,
        limit=clamp_tl(body.get("limit", 20), db_user),
        max_id=body.get("untilId"),
        since_id=body.get("sinceId"),
    )
    return masto_statuses_to_mk_notes(statuses)
