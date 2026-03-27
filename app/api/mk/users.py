"""
/api/users/*, /api/following/*, /api/blocking/*, /api/muting/*
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limit_utils import clamp_other, clamp_tl
from app.db.database import get_db
from app.services.note_converter import masto_statuses_to_mk_notes
from app.services.user_converter import masto_to_misskey_user_detailed
from app.api.mk.helpers import (
    _body,
    _token,
    _mastodon_client,
    _mastodon_client_with_user,
    _mk_client,
    _mk_follow_relationship,
)

router = APIRouter()


@router.post("/users/show")
async def api_users_show(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk = await _mastodon_client(token, db)
    if "userId" in body:
        account = await mk.get_account(body["userId"])
    else:
        username = body.get("username", "")
        host = body.get("host")
        query = f"{username}@{host}" if host else username
        results = await mk.search_accounts(query, limit=1)
        account = results[0] if results else {}
    return masto_to_misskey_user_detailed(account)


@router.post("/users/search")
async def api_users_search(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk, db_user = await _mastodon_client_with_user(token, db)
    accounts = await mk.search_accounts(body.get("query", ""), limit=clamp_other(body.get("limit", 20), db_user))
    return [masto_to_misskey_user_detailed(a) for a in accounts]


@router.post("/users/followers")
async def api_users_followers(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk, db_user = await _mastodon_client_with_user(token, db)
    me = await mk.verify_credentials()
    viewer_id = me.get("id", "")
    accounts = await mk.get_followers(body["userId"], limit=clamp_other(body.get("limit", 40), db_user))
    return [
        _mk_follow_relationship(a, viewer_id, is_following=False)
        for a in (accounts if isinstance(accounts, list) else [])
    ]


@router.post("/users/following")
async def api_users_following(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk, db_user = await _mastodon_client_with_user(token, db)
    me = await mk.verify_credentials()
    viewer_id = me.get("id", "")
    accounts = await mk.get_following(body["userId"], limit=clamp_other(body.get("limit", 40), db_user))
    return [
        _mk_follow_relationship(a, viewer_id, is_following=True)
        for a in (accounts if isinstance(accounts, list) else [])
    ]


@router.post("/users/notes")
async def api_users_notes(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    mk, db_user = await _mastodon_client_with_user(token, db)
    statuses = await mk.get_account_statuses(body["userId"], limit=clamp_tl(body.get("limit", 20), db_user))
    return masto_statuses_to_mk_notes(statuses)


@router.post("/following/create")
async def api_following_create(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).follow(body["userId"])


@router.post("/following/delete")
async def api_following_delete(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).unfollow(body["userId"])


@router.post("/blocking/create")
async def api_blocking_create(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).block(body["userId"])


@router.post("/blocking/delete")
async def api_blocking_delete(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).unblock(body["userId"])


@router.post("/blocking/list")
async def api_blocking_list(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    _, db_user = await _mastodon_client_with_user(token, db)
    return await _mk_client(token).get_blocks(limit=clamp_other(body.get("limit", 40), db_user))


@router.post("/muting/create")
async def api_muting_create(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).mute(body["userId"])


@router.post("/muting/delete")
async def api_muting_delete(request: Request):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    return await _mk_client(token).unmute(body["userId"])


@router.post("/muting/list")
async def api_muting_list(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    _, db_user = await _mastodon_client_with_user(token, db)
    return await _mk_client(token).get_mutes(limit=clamp_other(body.get("limit", 40), db_user))
