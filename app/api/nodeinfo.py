"""
NodeInfo 2.0 endpoint.

Spec: https://nodeinfo.diaspora.software/ns/schema/2.0

Discovery:  GET /.well-known/nodeinfo  → links to /nodeinfo/2.0
Data:       GET /nodeinfo/2.0          → actual nodeinfo document
"""

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings

router = APIRouter(tags=["nodeinfo"])


def _is_dart_client(request: Request) -> bool:
    ua = request.headers.get("user-agent", "")
    return ua.lower().startswith("dart/")


def _proxy_base(request: Request) -> str:
    """
    自プロキシのベース URL を決定する。
    PROXY_BASE_URL が設定されていればそれを使い、
    なければリクエストの base_url から自動検出する。
    """
    if settings.PROXY_BASE_URL:
        return settings.PROXY_BASE_URL.rstrip("/")
    # Request.base_url は "http://host:port/" 形式
    return str(request.base_url).rstrip("/")


@router.get("/.well-known/nodeinfo")
async def nodeinfo_discovery(request: Request):
    """
    Well-known discovery document。
    Dart クライアント以外からのアクセスは 404 を返す。
    """
    if not _is_dart_client(request):
        return JSONResponse(status_code=404, content={"error": "Not Found"})
    base = _proxy_base(request)
    return {
        "links": [
            {
                "rel": "http://nodeinfo.diaspora.software/ns/schema/2.0",
                "href": f"{base}/nodeinfo/2.0",
            }
        ]
    }


@router.get("/nodeinfo/2.0")
async def nodeinfo(request: Request):
    """
    NodeInfo 2.0 document。
    Dart クライアント以外からのアクセスは 404 を返す。
    Misskey の /api/stats を叩いてユーザー数・投稿数を取得する。
    取得失敗時はゼロにフォールバックする。
    """
    if not _is_dart_client(request):
        return JSONResponse(status_code=404, content={"error": "Not Found"})
    user_count = 0
    post_count = 0
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{settings.MASTODON_INSTANCE_URL}/api/stats", json={}
            )
            if resp.status_code == 200:
                stats = resp.json()
                user_count = stats.get("originalUsersCount", 0)
                post_count = stats.get("originalNotesCount", 0)
    except Exception:
        pass

    return {
        "version": "2.0",
        "software": {
            "name": "misskey-mastodon-proxy",
            "version": settings.INSTANCE_VERSION,
        },
        "protocols": ["activitypub"],
        "usage": {
            "users": {
                "total": user_count,
                "activeHalfyear": None,
                "activeMonth": None,
            },
            "localPosts": post_count,
        },
        "openRegistrations": False,
        "metadata": {
            "nodeName": settings.INSTANCE_TITLE,
            "nodeDescription": settings.INSTANCE_DESCRIPTION,
            "upstream": settings.MASTODON_INSTANCE_URL,
            # Fedibird 互換フラグ
            "features": [
                "emoji_reaction",
                "emoji_reaction_streaming",
            ],
        },
    }
