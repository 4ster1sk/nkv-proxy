"""
/api/i/*, /api/notifications/*, /api/miauth/*
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.mk.helpers import (
    _body,
    _mastodon_client,
    _mastodon_client_with_user,
    _mk_client,
    _token,
)
from app.core.limit_utils import clamp_notifications, clamp_other
from app.db import crud
from app.db.database import get_db
from app.db.models import OAuthToken
from app.services.note_converter import (
    masto_notification_to_mk,
    masto_statuses_to_mk_notes,
)
from app.services.user_converter import masto_to_misskey_user_detailed

router = APIRouter()


@router.post("/i")
async def api_i(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Misskey の /api/i 互換エンドポイント。
    Mastodon の GET /api/v1/accounts/verify_credentials に変換して返す。
    """
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")

    result = await crud.get_token_with_user(db, token)
    db_user = result[1] if result else None

    mk_client = await _mastodon_client(token, db)
    masto_user = await mk_client.verify_credentials()
    return masto_to_misskey_user_detailed(masto_user, db_user=db_user, is_me=True)


_MK_TO_MASTO_PROFILE: dict[str, str] = {
    "name": "display_name",
    "description": "note",
    "isBot": "bot",
    "isCat": "is_cat",
    "isLocked": "locked",
    "birthday": "birthday",
}


@router.post("/i/update")
async def api_i_update(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")

    result = await crud.get_token_with_user(db, token)
    db_user = result[1] if result else None

    payload = {}
    for mk_key, masto_key in _MK_TO_MASTO_PROFILE.items():
        if mk_key in body:
            payload[masto_key] = body[mk_key]

    instance_url = db_user.mastodon_instance if db_user else None
    encoding = "multipart"
    if instance_url:
        masto_app = await crud.get_mastodon_app(db, instance_url)
        if masto_app:
            encoding = masto_app.update_credentials_encoding

    mk_client = await _mastodon_client(token, db)
    masto_user = await mk_client.update_credentials(encoding=encoding, **payload)
    return masto_to_misskey_user_detailed(masto_user, db_user=db_user, is_me=True)


@router.post("/i/notifications")
async def api_i_notifications(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk_client, db_user = await _mastodon_client_with_user(token, db)
    params: dict = {"limit": clamp_notifications(body.get("limit", 20), db_user)}
    if body.get("sinceId"):
        params["min_id"] = body["sinceId"]
    if body.get("untilId"):
        params["max_id"] = body["untilId"]
    masto_notifs = await mk_client.get_notifications(**params)
    return [n for n in (masto_notification_to_mk(raw) for raw in masto_notifs) if n is not None]


@router.post("/i/favorites")
async def api_i_favorites(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk_client, db_user = await _mastodon_client_with_user(token, db)
    params: dict = {"limit": clamp_other(body.get("limit", 20), db_user)}
    if body.get("sinceId"):
        params["min_id"] = body["sinceId"]
    if body.get("untilId"):
        params["max_id"] = body["untilId"]
    statuses = await mk_client.get_bookmarks(**params)
    notes = masto_statuses_to_mk_notes(statuses)
    return [
        {
            "id": note["id"],
            "createdAt": note["createdAt"],
            "noteId": note["id"],
            "note": note,
        }
        for note in notes
    ]


@router.post("/notifications/mark-all-as-read")
async def api_notifications_mark_all_read(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).clear_notifications()


@router.post("/miauth/{session_id}/check")
async def api_miauth_check(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    このプロキシ自身が miAuth 発行元のため、
    上流ではなく DB から session を取得してトークンを返す。
    Misskey 互換レスポンス: {"ok": true, "token": "...", "user": {...}}
    """
    session = await crud.get_miauth_session(db, session_id)

    if session is None or not session.authorized:
        return {"ok": False}

    result = await db.execute(
        sa_select(OAuthToken).where(
            OAuthToken.session_id == session_id,
            OAuthToken.revoked == False,  # noqa
        )
    )
    token = result.scalar_one_or_none()
    if token is None:
        return {"ok": False}

    user = await crud.get_user_by_id(db, session.user_id)
    if user is None:
        return {"ok": False}

    return {
        "ok": True,
        "token": token.access_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "name": user.display_name or user.username,
            "host": None,
            "avatarUrl": user.avatar_url,
            "isBot": user.is_bot,
            "isLocked": user.is_locked,
            "description": user.bio or "",
            "createdAt": user.created_at.isoformat() if user.created_at else "",
            "followersCount": 0,
            "followingCount": 0,
            "notesCount": 0,
            "emojis": [],
            "fields": [],
        },
    }
