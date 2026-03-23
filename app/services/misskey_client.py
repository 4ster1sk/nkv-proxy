"""
Thin async wrapper around the Misskey API.
All methods accept an `i` (token) and forward to the Misskey instance.
"""

from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.core.config import settings


class MisskeyClient:
    def __init__(self, token: str):
        self.token = token
        self.base = settings.MASTODON_INSTANCE_URL

    async def _post(self, endpoint: str, **kwargs) -> dict:
        payload = {"i": self.token, **kwargs}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self.base}/api/{endpoint}", json=payload)
        if resp.status_code == 204:
            return {}
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

    # ---- Account ----

    async def get_i(self) -> dict:
        return await self._post("i")

    async def update_i(self, **kwargs) -> dict:
        return await self._post("i/update", **kwargs)

    # ---- Notes ----

    async def create_note(
        self,
        text: str | None = None,
        cw: str | None = None,
        visibility: str = "public",
        reply_id: str | None = None,
        renote_id: str | None = None,
        file_ids: list[str] | None = None,
        poll: dict | None = None,
    ) -> dict:
        payload: dict = {"visibility": visibility}
        if text:
            payload["text"] = text
        if cw is not None:
            payload["cw"] = cw
        if reply_id:
            payload["replyId"] = reply_id
        if renote_id:
            payload["renoteId"] = renote_id
        if file_ids:
            payload["fileIds"] = file_ids
        if poll:
            payload["poll"] = poll
        return await self._post("notes/create", **payload)

    async def delete_note(self, note_id: str) -> dict:
        return await self._post("notes/delete", noteId=note_id)

    async def get_note(self, note_id: str) -> dict:
        return await self._post("notes/show", noteId=note_id)

    async def notes_timeline(self, limit: int = 20, since_id: str | None = None, max_id: str | None = None) -> list:
        payload: dict = {"limit": limit}
        if since_id:
            payload["sinceId"] = since_id
        if max_id:
            payload["untilId"] = max_id
        return await self._post("notes/timeline", **payload)  # type: ignore

    async def notes_local_timeline(self, limit: int = 20, since_id: str | None = None, max_id: str | None = None) -> list:
        payload: dict = {"limit": limit}
        if since_id:
            payload["sinceId"] = since_id
        if max_id:
            payload["untilId"] = max_id
        return await self._post("notes/local-timeline", **payload)  # type: ignore

    async def notes_global_timeline(self, limit: int = 20, since_id: str | None = None, max_id: str | None = None) -> list:
        payload: dict = {"limit": limit}
        if since_id:
            payload["sinceId"] = since_id
        if max_id:
            payload["untilId"] = max_id
        return await self._post("notes/global-timeline", **payload)  # type: ignore

    async def note_context(self, note_id: str) -> dict:
        return await self._post("notes/children", noteId=note_id, limit=40)

    async def note_reply_context(self, note_id: str) -> dict:
        note = await self.get_note(note_id)
        ancestors = []
        cur = note
        while cur.get("replyId"):
            cur = await self.get_note(cur["replyId"])
            ancestors.insert(0, cur)
        return {"ancestors": ancestors, "descendants": []}

    # ---- Favourites / Reactions ----

    async def create_reaction(self, note_id: str, reaction: str = "❤") -> dict:
        return await self._post("notes/reactions/create", noteId=note_id, reaction=reaction)

    async def delete_reaction(self, note_id: str) -> dict:
        return await self._post("notes/reactions/delete", noteId=note_id)

    async def note_reactions(self, note_id: str) -> list:
        return await self._post("notes/reactions", noteId=note_id, limit=100)  # type: ignore

    # ---- Renote (Boost) ----

    async def renote(self, note_id: str) -> dict:
        return await self._post("notes/create", renoteId=note_id)

    async def unrenote(self, note_id: str) -> dict:
        # Find own renote then delete
        notes = await self._post("notes/renotes", noteId=note_id, limit=10)
        for n in (notes or []):  # type: ignore
            if n.get("userId") == (await self.get_i()).get("id"):
                return await self.delete_note(n["id"])
        return {}

    # ---- Following ----

    async def follow(self, user_id: str) -> dict:
        return await self._post("following/create", userId=user_id)

    async def unfollow(self, user_id: str) -> dict:
        return await self._post("following/delete", userId=user_id)

    async def get_followers(self, user_id: str, limit: int = 40) -> list:
        return await self._post("users/followers", userId=user_id, limit=limit)  # type: ignore

    async def get_following(self, user_id: str, limit: int = 40) -> list:
        return await self._post("users/following", userId=user_id, limit=limit)  # type: ignore

    # ---- Blocks / Mutes ----

    async def block(self, user_id: str) -> dict:
        return await self._post("blocking/create", userId=user_id)

    async def unblock(self, user_id: str) -> dict:
        return await self._post("blocking/delete", userId=user_id)

    async def mute(self, user_id: str) -> dict:
        return await self._post("muting/create", userId=user_id)

    async def unmute(self, user_id: str) -> dict:
        return await self._post("muting/delete", userId=user_id)

    async def get_blocks(self, limit: int = 40) -> list:
        return await self._post("blocking/list", limit=limit)  # type: ignore

    async def get_mutes(self, limit: int = 40) -> list:
        return await self._post("muting/list", limit=limit)  # type: ignore

    # ---- Notifications ----

    async def get_notifications(self, limit: int = 20, since_id: str | None = None, max_id: str | None = None) -> list:
        payload: dict = {"limit": limit}
        if since_id:
            payload["sinceId"] = since_id
        if max_id:
            payload["untilId"] = max_id
        return await self._post("i/notifications", **payload)  # type: ignore

    async def clear_notifications(self) -> dict:
        return await self._post("notifications/mark-all-as-read")

    # ---- Search ----

    async def search_notes(self, query: str, limit: int = 20) -> list:
        return await self._post("notes/search", query=query, limit=limit)  # type: ignore

    async def search_users(self, query: str, limit: int = 20) -> list:
        return await self._post("users/search", query=query, limit=limit)  # type: ignore

    # ---- Users ----

    async def get_user(self, user_id: str) -> dict:
        return await self._post("users/show", userId=user_id)

    async def get_user_by_username(self, username: str, host: str | None = None) -> dict:
        payload: dict = {"username": username}
        if host:
            payload["host"] = host
        return await self._post("users/show", **payload)

    async def get_user_notes(self, user_id: str, limit: int = 20) -> list:
        return await self._post("users/notes", userId=user_id, limit=limit)  # type: ignore

    # ---- Bookmarks ----

    async def bookmark(self, note_id: str) -> dict:
        return await self._post("notes/favorites/create", noteId=note_id)

    async def unbookmark(self, note_id: str) -> dict:
        return await self._post("notes/favorites/delete", noteId=note_id)

    async def get_bookmarks(self, limit: int = 20) -> list:
        return await self._post("i/favorites", limit=limit)  # type: ignore

    # ---- Instance info ----

    async def get_meta(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self.base}/api/meta", json={})
        return resp.json()

    async def get_emojis(self) -> list:
        data = await self._post("emojis")
        return data.get("emojis", [])  # type: ignore

    # ---- Antenna stub ----

    async def get_antennas(self) -> list:
        """Misskey has antennas but we return empty list per spec (role limit = 0)."""
        return []
