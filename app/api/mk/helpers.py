"""
共通ヘルパー関数・依存関係。
各ドメインモジュールからインポートして使用する。
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.services.mastodon_client import MastodonClient
from app.services.misskey_client import MisskeyClient
from app.services.user_converter import masto_to_misskey_user_detailed


async def _check_admin_allowed(token: str, db: AsyncSession) -> None:
    """
    /api/admin/* エンドポイントの冒頭で呼ぶ。
    - OAuthToken 以外（ApiKey 等）は 401
    - admin スコープ（read:admin / write:admin / admin: 系）を持たない場合は 403
    - admin_restricted=True の場合は 403
    """
    result = await crud.get_token_with_user(db, token)
    if result is None:
        raise HTTPException(status_code=401, detail="Credential required")
    token_obj, _ = result
    scopes = token_obj.scopes.replace(",", " ").split()
    has_admin_scope = any(
        s.startswith(("read:admin", "write:admin", "admin:")) for s in scopes
    )
    if not has_admin_scope:
        raise HTTPException(
            status_code=403,
            detail="This token does not have admin scope."
        )
    if token_obj.admin_restricted:
        raise HTTPException(
            status_code=403,
            detail="Admin API access is temporarily disabled for this token. "
                   "Re-enable it from the dashboard."
        )


def _mk_follow_relationship(
    account: dict,
    viewer_id: str,
    is_following: bool,
) -> dict:
    """
    Mastodon account → Misskey フォロー/フォロワー関係オブジェクト。

    Mastodon は createdAt や followerId を返さないため:
    - id        : UUIDv5(viewer_id + account_id) で決定論的に生成
    - createdAt : account.created_at を近似値として使用
    - followerId/followeeId : is_following の向きで決定
    """
    import uuid as _uuid
    account_id = account.get("id", "")
    seed = f"{viewer_id}:{account_id}"
    rel_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, seed))
    created_at = account.get("created_at", "")

    if is_following:
        follower_id = viewer_id
        followee_id = account_id
        followee = masto_to_misskey_user_detailed(account)
        follower = None
    else:
        follower_id = account_id
        followee_id = viewer_id
        followee = None
        follower = masto_to_misskey_user_detailed(account)

    return {
        "id": rel_id,
        "createdAt": created_at,
        "followeeId": followee_id,
        "followerId": follower_id,
        "followee": followee,
        "follower": follower,
    }


async def _body(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _token(body: dict, request: Request) -> str | None:
    if body.get("i"):
        return body["i"]
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


async def _mastodon_client_with_user(token: str, db: AsyncSession) -> "tuple[MastodonClient, Any]":
    """
    access_token または api_key → (MastodonClient, User) を返す。
    Mastodon未連携の場合は 403。
    """
    from app.db.models import User as _User

    result = await crud.get_token_with_user(db, token)
    if result is None:
        api_key_obj = await crud.get_api_key_by_key(db, token)
        if api_key_obj is None:
            raise HTTPException(status_code=401, detail="Invalid or revoked token")
        from sqlalchemy import select as _sel
        user_result = await db.execute(_sel(_User).where(_User.id == api_key_obj.user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
    else:
        _, user = result

    if not user.mastodon_token:
        raise HTTPException(
            status_code=403,
            detail="Mastodon連携が未設定です。ダッシュボードで連携してください。"
        )
    return MastodonClient(user.mastodon_token, user.mastodon_instance), user


async def _mastodon_client(token: str, db: AsyncSession) -> "MastodonClient":
    """互換ラッパー: MastodonClient のみを返す。"""
    client, _ = await _mastodon_client_with_user(token, db)
    return client


def _mk_client(token: str) -> MisskeyClient:
    """旧来のMisskeyClientが必要なエンドポイント用（将来的に削除予定）"""
    return MisskeyClient(token)


