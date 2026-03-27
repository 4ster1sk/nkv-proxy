"""
/api/admin/* — 管理者 API（admin_restricted フラグで一時無効化可能）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.mk.helpers import (
    _body,
    _check_admin_allowed,
    _mastodon_client,
    _token,
)
from app.db.database import get_db

router = APIRouter()


@router.post("/admin/show-users")
async def api_admin_show_users(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    mk = await _mastodon_client(token, db)
    accounts = await mk._get("admin/accounts", params={
        "limit": body.get("limit", 20),
        "origin": body.get("origin", "local"),
    })
    return accounts if isinstance(accounts, list) else []


@router.post("/admin/show-user")
async def api_admin_show_user(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    mk = await _mastodon_client(token, db)
    return await mk._get(f"admin/accounts/{body['userId']}")


@router.post("/admin/suspend-user")
async def api_admin_suspend_user(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    mk = await _mastodon_client(token, db)
    await mk._post(f"admin/accounts/{body['userId']}/action",
                   json={"type": "suspend"})
    return {}


@router.post("/admin/unsuspend-user")
async def api_admin_unsuspend_user(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    mk = await _mastodon_client(token, db)
    await mk._post(f"admin/accounts/{body['userId']}/unsuspend")
    return {}


@router.post("/admin/get-index-stats")
async def api_admin_index_stats(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    return []


@router.post("/admin/get-table-stats")
async def api_admin_table_stats(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    return {}


@router.post("/admin/server-info")
async def api_admin_server_info(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    return {"machine": "proxy", "cpu": {}, "mem": {}, "fs": {}, "net": {}}


@router.post("/admin/abuse-user-reports")
async def api_admin_abuse_reports(request: Request, db: AsyncSession = Depends(get_db)):
    body = await _body(request)
    token = _token(body, request)
    if not token:
        raise HTTPException(status_code=401, detail="Credential required")
    await _check_admin_allowed(token, db)
    mk = await _mastodon_client(token, db)
    try:
        reports = await mk._get("admin/reports", params={"limit": body.get("limit", 20)})
        return reports if isinstance(reports, list) else []
    except Exception:
        return []
