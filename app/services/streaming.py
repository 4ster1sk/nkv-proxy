"""
Misskey WebSocket ストリーミング互換レイヤー

方向:
  Miria (Misskey WS) ← ws://proxy/streaming?i=<token>
  上流 Mastodon SSE  → GET https://mastodon.social/api/v1/streaming?stream=user
"""

from __future__ import annotations
import asyncio
import json
import logging
from typing import AsyncGenerator

import httpx
from fastapi import WebSocket, WebSocketDisconnect

from app.services.note_converter import masto_status_to_mk_note

logger = logging.getLogger(__name__)

CHANNEL_TO_STREAM: dict[str, str] = {
    "homeTimeline":   "user",          # /streaming/user (TL + 通知)
    "main":           "user",          # /streaming/user (通知含む)
    "notifications":  "user",          # /streaming/user (通知含む)
    "localTimeline":  "public",        # /streaming/public (Nekonoverse に /public/local はない)
    "globalTimeline": "public",        # /streaming/public
    "hybridTimeline": "public",        # /streaming/public
    "messaging":      "",
    "drive":          "",
}


def _masto_notification_to_mk(data: dict) -> dict:
    type_map = {
        "mention": "reply", "reblog": "renote", "favourite": "reaction",
        "follow": "follow", "poll": "pollEnded", "update": "noteUpdated",
    }
    mk_type = type_map.get(data.get("type", ""), "mention")
    account = data.get("account") or {}
    notifier = {
        "id": account.get("id", ""), "username": account.get("username", ""),
        "name": account.get("display_name") or account.get("username", ""),
        "host": None, "avatarUrl": account.get("avatar"),
        "isBot": account.get("bot", False), "isCat": False,
        "emojis": {}, "onlineStatus": "unknown",
        "badgeRoles": [], "avatarDecorations": [],
    }
    result: dict = {
        "id": data.get("id", ""), "createdAt": data.get("created_at", ""),
        "type": mk_type, "userId": account.get("id", ""), "user": notifier,
    }
    if data.get("status"):
        result["note"] = masto_status_to_mk_note(data["status"])
    return result


async def _mastodon_sse_stream(
    mastodon_token: str, mastodon_instance: str, stream: str,
) -> AsyncGenerator[tuple[str, dict], None]:
    """Mastodon SSE を購読して (event_name, data_dict) を yield する。切断時は再接続。"""
    # Mastodon SSE はパスベース: /api/v1/streaming/user, /api/v1/streaming/public etc.
    stream_path = stream.replace(":", "/")  # "public:local" → "public/local"
    url = f"{mastodon_instance}/api/v1/streaming/{stream_path}"
    headers: dict = {}
    if mastodon_token:
        headers["Authorization"] = f"Bearer {mastodon_token}"
    params: dict = {}  # クエリパラメータ不要（パスで指定）

    while True:
        try:
            logger.debug("Mastodon SSE connect: %s?stream=%s", url, stream)
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url, headers=headers, params=params) as resp:
                    if resp.status_code != 200:
                        logger.warning("Mastodon SSE %s returned %d", url, resp.status_code)
                        await asyncio.sleep(5)
                        continue
                    event_name = ""
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            event_name = ""
                            continue
                        if line.startswith(":"):
                            continue
                        if line.startswith("event:"):
                            event_name = line[6:].strip()
                        elif line.startswith("data:"):
                            raw = line[5:].strip()
                            if not raw or raw == "null":
                                continue
                            try:
                                data = json.loads(raw)
                            except json.JSONDecodeError:
                                data = {"raw": raw}
                            if event_name:
                                yield event_name, data
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("Mastodon SSE error (%s): %s — reconnect in 5s", stream, exc)
            await asyncio.sleep(5)


class MisskeyStreamingProxy:
    """1本の Misskey WebSocket 接続を管理し、Mastodon SSE に変換する。"""

    def __init__(self, websocket: WebSocket, mastodon_token: str, mastodon_instance: str):
        self.ws = websocket
        self.mastodon_token = mastodon_token
        self.mastodon_instance = mastodon_instance.rstrip("/")
        self._channels: dict[str, str] = {}
        self._stream_channels: dict[str, set] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def run(self) -> None:
        await self.ws.accept()
        logger.debug("Misskey WS client connected")
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(self.ws.receive_text(), timeout=30)
                except asyncio.TimeoutError:
                    try:
                        await self.ws.send_text(json.dumps({"type": "ping"}))
                    except Exception:
                        break
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg_type = msg.get("type", "")
                body = msg.get("body", {})
                if msg_type == "connect":
                    await self._handle_connect(body)
                elif msg_type == "disconnect":
                    await self._handle_disconnect(body)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.warning("Misskey WS loop error: %s", exc)
        finally:
            await self._cleanup()

    async def _handle_connect(self, body: dict) -> None:
        channel_name = body.get("channel", "")
        channel_id = body.get("id", "")
        stream_name = CHANNEL_TO_STREAM.get(channel_name, "")
        self._channels[channel_id] = stream_name
        await self._send({"type": "connected", "body": {"id": channel_id}})
        logger.debug("Channel connect: %s → %s (id=%s)", channel_name, stream_name, channel_id)
        if not stream_name:
            return
        if stream_name not in self._tasks:
            self._stream_channels[stream_name] = set()
            task = asyncio.create_task(
                self._sse_to_ws(stream_name), name=f"sse-{stream_name}"
            )
            self._tasks[stream_name] = task
        self._stream_channels.setdefault(stream_name, set()).add(channel_id)

    async def _handle_disconnect(self, body: dict) -> None:
        channel_id = body.get("id", "")
        stream_name = self._channels.pop(channel_id, "")
        if stream_name and stream_name in self._stream_channels:
            self._stream_channels[stream_name].discard(channel_id)
            if not self._stream_channels[stream_name]:
                task = self._tasks.pop(stream_name, None)
                if task:
                    task.cancel()
                del self._stream_channels[stream_name]

    async def _sse_to_ws(self, stream_name: str) -> None:
        try:
            async for event_name, data in _mastodon_sse_stream(
                self.mastodon_token, self.mastodon_instance, stream_name
            ):
                channel_ids = self._stream_channels.get(stream_name, set())
                if not channel_ids:
                    continue
                mk_event, mk_body = self._convert_event(event_name, data)
                if mk_event is None:
                    continue
                for cid in list(channel_ids):
                    await self._send({
                        "type": "channel",
                        "body": {"id": cid, "type": mk_event, "body": mk_body},
                    })
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("SSE->WS task error (%s): %s", stream_name, exc)

    def _convert_event(self, event_name: str, data: dict):
        if event_name == "update":
            return "note", masto_status_to_mk_note(data)
        if event_name == "notification":
            return "notification", _masto_notification_to_mk(data)
        if event_name == "delete":
            return "noteDeleted", {"deletedNoteId": str(data)}
        if event_name == "status.updated":
            return "noteUpdated", masto_status_to_mk_note(data)
        if event_name == "filters_changed":
            return "meUpdated", {}
        return None, {}

    async def _send(self, payload: dict) -> None:
        try:
            await self.ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            logger.debug("WS send error: %s", exc)

    async def _cleanup(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        try:
            await self.ws.close()
        except Exception:
            pass
        logger.debug("Misskey WS client disconnected")


async def stream_to_sse(
    token: str,
    stream_name: str,
    instance_url: str,
    extra_params: dict | None = None,
) -> AsyncGenerator[str, None]:
    """Mastodon SSE をプロキシして SSE 形式で返す。"""
    url = f"{instance_url}/api/v1/streaming"
    headers: dict = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params: dict = {"stream": stream_name}
    if extra_params:
        params.update(extra_params)
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url, headers=headers, params=params) as resp:
                if resp.status_code != 200:
                    import json as _j
                    yield f"event: error\ndata: {_j.dumps({'error': f'upstream {resp.status_code}'})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    yield line + "\n"
    except Exception as exc:
        import json as _j
        logger.warning("SSE proxy error: %s", exc)
        yield f"event: error\ndata: {_j.dumps({'error': str(exc)})}\n\n"


async def handle_ws_stream(
    websocket: WebSocket,
    token: str,
    stream_name: str,
    instance_url: str,
    extra_params: dict | None = None,
) -> None:
    """Misskey WebSocket -> Mastodon SSE 変換のメインエントリ。"""
    from app.db.database import AsyncSessionLocal
    from app.db import crud
    from app.db.models import User
    from sqlalchemy import select

    mastodon_token = ""
    mastodon_instance = instance_url

    if token:
        async with AsyncSessionLocal() as db:
            result = await crud.get_token_with_user(db, token)
            if result and result[1].mastodon_token:
                mastodon_token = result[1].mastodon_token
                mastodon_instance = result[1].mastodon_instance or instance_url
            else:
                ak = await crud.get_api_key_by_key(db, token)
                if ak:
                    u = (await db.execute(
                        select(User).where(User.id == ak.user_id)
                    )).scalar_one_or_none()
                    if u and u.mastodon_token:
                        mastodon_token = u.mastodon_token
                        mastodon_instance = u.mastodon_instance or instance_url

    proxy = MisskeyStreamingProxy(websocket, mastodon_token, mastodon_instance)
    await proxy.run()
