"""
Mastodon-compatible streaming API backed by Misskey's WebSocket streaming.

Mastodon streaming endpoint: GET /api/v1/streaming?stream=<name>&access_token=<token>
We connect to Misskey's ws://<host>/streaming?i=<token> and translate events.

Fedibird emoji_reaction events are forwarded as-is on the "update" stream.
"""

from __future__ import annotations
import asyncio
import json
import logging
from typing import AsyncGenerator

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from app.core.config import settings
from app.services.converter import mk_note_to_status, mk_notification_to_mastodon

logger = logging.getLogger(__name__)

# Map Mastodon stream name → Misskey channel name
STREAM_CHANNEL_MAP = {
    "user": "main",
    "user:notification": "main",
    "public": "globalTimeline",
    "public:local": "localTimeline",
    "public:remote": "hybridTimeline",
    "hashtag": "hashtag",
    "hashtag:local": "hashtag",
    "list": "userList",
    "direct": "main",
}


def _mk_event_to_mastodon(event_type: str, body: dict, instance_url: str) -> tuple[str, str] | None:
    """
    Convert a Misskey channel event to a Mastodon SSE event+payload pair.
    Returns (event_name, json_payload) or None to skip.
    """
    if event_type == "note":
        status = mk_note_to_status(body, instance_url)
        return ("update", json.dumps(status))

    if event_type == "notification":
        notif = mk_notification_to_mastodon(body, instance_url)
        if not notif:
            return None
        return ("notification", json.dumps(notif))

    if event_type == "unreadNotificationsCount":
        return None  # not a standard Mastodon event

    if event_type == "meUpdated":
        return None

    if event_type == "reaction":
        # Fedibird-style status_updated event
        # body: {id, reaction, user}
        note_id = body.get("id", "")
        payload = {
            "event": "status.updated",
            "emoji_reaction": {
                "name": body.get("reaction", ""),
                "count": body.get("count", 1),
                "me": False,
            },
            "id": note_id,
        }
        return ("status.updated", json.dumps(payload))

    if event_type == "follow":
        return ("filters_changed", "")

    return None


async def _misskey_ws_connect(token: str, channel: str, extra_params: dict | None = None):
    """Yield decoded Misskey channel messages from WebSocket."""
    ws_url = settings.MASTODON_INSTANCE_URL.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_url}/streaming?i={token}"
    channel_id = "proxy-main"
    subscribe_msg = {
        "type": "connect",
        "body": {
            "channel": channel,
            "id": channel_id,
            **(extra_params or {}),
        },
    }

    async with websockets.connect(ws_url, ping_interval=20) as ws:
        await ws.send(json.dumps(subscribe_msg))
        async for raw in ws:
            try:
                msg = json.loads(raw)
                if msg.get("type") == "channel" and msg["body"].get("id") == channel_id:
                    yield msg["body"]["type"], msg["body"].get("body", {})
            except (json.JSONDecodeError, KeyError):
                continue


async def stream_to_sse(
    token: str,
    stream_name: str,
    instance_url: str,
    extra_params: dict | None = None,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted strings for a given Mastodon stream.
    Usage: StreamingResponse(stream_to_sse(...), media_type="text/event-stream")
    """
    channel = STREAM_CHANNEL_MAP.get(stream_name, "globalTimeline")
    try:
        async for event_type, body in _misskey_ws_connect(token, channel, extra_params):
            result = _mk_event_to_mastodon(event_type, body, instance_url)
            if result is None:
                continue
            masto_event, payload = result
            yield f"event: {masto_event}\ndata: {payload}\n\n"
    except Exception as exc:
        logger.warning("WebSocket stream error: %s", exc)
        yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"


async def handle_ws_stream(
    websocket: WebSocket,
    token: str,
    stream_name: str,
    instance_url: str,
    extra_params: dict | None = None,
) -> None:
    """Handle a native WebSocket connection from a Mastodon client."""
    await websocket.accept()
    channel = STREAM_CHANNEL_MAP.get(stream_name, "globalTimeline")
    try:
        async for event_type, body in _misskey_ws_connect(token, channel, extra_params):
            result = _mk_event_to_mastodon(event_type, body, instance_url)
            if result is None:
                continue
            masto_event, payload = result
            await websocket.send_text(json.dumps({"event": masto_event, "payload": payload}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WS handler error: %s", exc)
        try:
            await websocket.send_text(json.dumps({"error": str(exc)}))
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
