"""
Mastodon streaming API.

SSE:       GET /api/v1/streaming?stream=<name>&access_token=<token>
WebSocket: GET /api/v1/streaming  (Upgrade: websocket)
"""

from fastapi import APIRouter, Query, Request, WebSocket
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.services.streaming import handle_ws_stream, stream_to_sse

router = APIRouter(prefix="/api/v1/streaming", tags=["streaming"])


@router.get("/health")
async def streaming_health():
    return {"healthy": True}


@router.get("")
async def streaming_sse(
    request: Request,
    stream: str = Query("public"),
    access_token: str = Query(None),
    list: str = Query(None),
    tag: str = Query(None),
):
    """Server-Sent Events streaming endpoint."""
    # Token can come from query param or Authorization header
    token = access_token
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]

    extra: dict = {}
    if list:
        extra["listId"] = list
    if tag:
        extra["q"] = tag

    return StreamingResponse(
        stream_to_sse(token or "", stream, settings.MASTODON_INSTANCE_URL, extra),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.websocket("")
async def streaming_ws(
    websocket: WebSocket,
    stream: str = Query("public"),
    access_token: str = Query(None),
):
    """WebSocket streaming endpoint."""
    await handle_ws_stream(websocket, access_token or "", stream, settings.MASTODON_INSTANCE_URL)
