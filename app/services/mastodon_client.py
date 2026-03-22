"""
上流 Mastodon API クライアント。

User.mastodon_token と User.mastodon_instance を使って
上流 Mastodon インスタンスに Mastodon API リクエストを転送する。
"""

from __future__ import annotations
import logging
import httpx
from fastapi import HTTPException
from app.core.config import settings


logger = logging.getLogger(__name__)


class MastodonClient:
    def __init__(self, token: str, instance: str | None = None):
        self.token = token
        self.base = (instance or settings.MASTODON_INSTANCE_URL).rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        url = f"{self.base}/api/v1/{path}"
        logger.debug("Mastodon GET %s params=%s", url, params)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url,
                headers=self.headers,
                params=params or {},
            )
        if resp.status_code == 204:
            return {}
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

    async def _post(self, path: str, json: dict | None = None, data: dict | None = None) -> dict | list:
        url = f"{self.base}/api/v1/{path}"
        logger.debug("Mastodon POST %s", url)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                headers=self.headers,
                json=json,
                data=data,
            )
        if resp.status_code == 204:
            return {}
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

    async def _delete(self, path: str) -> dict | list:
        url = f"{self.base}/api/v1/{path}"
        logger.debug("Mastodon DELETE %s", url)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(
                url,
                headers=self.headers,
            )
        if resp.status_code == 204:
            return {}
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

    # ── Account ────────────────────────────────────────────────────────
    async def verify_credentials(self) -> dict:
        return await self._get("accounts/verify_credentials")  # type: ignore

    async def update_credentials(self, **kwargs) -> dict:
        return await self._post("accounts/update_credentials", data=kwargs)  # type: ignore

    async def get_account(self, account_id: str) -> dict:
        return await self._get(f"accounts/{account_id}")  # type: ignore

    async def get_account_statuses(self, account_id: str, **params) -> list:
        return await self._get(f"accounts/{account_id}/statuses", params=params)  # type: ignore

    async def get_followers(self, account_id: str, **params) -> list:
        return await self._get(f"accounts/{account_id}/followers", params=params)  # type: ignore

    async def get_following(self, account_id: str, **params) -> list:
        return await self._get(f"accounts/{account_id}/following", params=params)  # type: ignore

    async def follow(self, account_id: str) -> dict:
        return await self._post(f"accounts/{account_id}/follow")  # type: ignore

    async def unfollow(self, account_id: str) -> dict:
        return await self._post(f"accounts/{account_id}/unfollow")  # type: ignore

    async def block(self, account_id: str) -> dict:
        return await self._post(f"accounts/{account_id}/block")  # type: ignore

    async def unblock(self, account_id: str) -> dict:
        return await self._post(f"accounts/{account_id}/unblock")  # type: ignore

    async def mute(self, account_id: str) -> dict:
        return await self._post(f"accounts/{account_id}/mute")  # type: ignore

    async def unmute(self, account_id: str) -> dict:
        return await self._post(f"accounts/{account_id}/unmute")  # type: ignore

    async def search_accounts(self, q: str, limit: int = 40) -> list:
        return await self._get("accounts/search", params={"q": q, "limit": limit})  # type: ignore

    async def get_blocks(self, **params) -> list:
        return await self._get("blocks", params=params)  # type: ignore

    async def get_mutes(self, **params) -> list:
        return await self._get("mutes", params=params)  # type: ignore

    # ── Statuses ───────────────────────────────────────────────────────
    async def get_status(self, status_id: str) -> dict:
        return await self._get(f"statuses/{status_id}")  # type: ignore

    async def create_status(self, **kwargs) -> dict:
        return await self._post("statuses", json=kwargs)  # type: ignore

    async def delete_status(self, status_id: str) -> dict:
        return await self._delete(f"statuses/{status_id}")  # type: ignore

    async def get_context(self, status_id: str) -> dict:
        return await self._get(f"statuses/{status_id}/context")  # type: ignore

    async def favourite(self, status_id: str) -> dict:
        return await self._post(f"statuses/{status_id}/favourite")  # type: ignore

    async def unfavourite(self, status_id: str) -> dict:
        return await self._post(f"statuses/{status_id}/unfavourite")  # type: ignore

    async def reblog(self, status_id: str) -> dict:
        return await self._post(f"statuses/{status_id}/reblog")  # type: ignore

    async def unreblog(self, status_id: str) -> dict:
        return await self._post(f"statuses/{status_id}/unreblog")  # type: ignore

    async def bookmark(self, status_id: str) -> dict:
        return await self._post(f"statuses/{status_id}/bookmark")  # type: ignore

    async def unbookmark(self, status_id: str) -> dict:
        return await self._post(f"statuses/{status_id}/unbookmark")  # type: ignore

    # Fedibird emoji reactions
    async def add_emoji_reaction(self, status_id: str, emoji: str) -> dict:
        return await self._put(f"statuses/{status_id}/emoji_reactions/{emoji}")  # type: ignore

    async def remove_emoji_reaction(self, status_id: str, emoji: str) -> dict:
        return await self._delete(f"statuses/{status_id}/emoji_reactions/{emoji}")  # type: ignore

    async def _put(self, path: str) -> dict:
        url = f"{self.base}/api/v1/{path}"
        logger.debug("Mastodon PUT %s", url)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(
                url, headers=self.headers
            )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

    # ── Timelines ──────────────────────────────────────────────────────
    async def home_timeline(self, **params) -> list:
        clean = {k: v for k, v in params.items() if v is not None}
        return await self._get("timelines/home", params=clean)  # type: ignore

    async def public_timeline(self, **params) -> list:
        clean = {k: v for k, v in params.items() if v is not None}
        return await self._get("timelines/public", params=clean)  # type: ignore

    async def get_bookmarks(self, **params) -> list:
        return await self._get("bookmarks", params=params)  # type: ignore

    async def get_favourites(self, **params) -> list:
        return await self._get("favourites", params=params)  # type: ignore

    # ── Notifications ──────────────────────────────────────────────────
    async def get_notifications(self, **params) -> list:
        return await self._get("notifications", params=params)  # type: ignore

    async def clear_notifications(self) -> dict:
        return await self._post("notifications/clear")  # type: ignore

    # ── Search ─────────────────────────────────────────────────────────
    async def search(self, q: str, **params) -> dict:
        return await self._get("search", params={"q": q, **params})  # type: ignore

    # ── Instance ───────────────────────────────────────────────────────
    async def get_instance(self) -> dict:
        url = f"{self.base}/api/v1/instance"
        logger.debug("Mastodon GET %s", url)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
        return resp.json() if resp.status_code == 200 else {}

    async def get_custom_emojis(self) -> list:
        url = f"{self.base}/api/v1/custom_emojis"
        logger.debug("Mastodon GET %s", url)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
        return resp.json() if resp.status_code == 200 else []
