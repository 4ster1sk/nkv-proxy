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

    async def get_accounts(self, ids: list[str]) -> list:
        return await self._get("accounts", params={"id[]": ids})  # type: ignore

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

    # ── Lists ──────────────────────────────────────────────────────────
    async def get_lists(self) -> list:
        return await self._get("lists")  # type: ignore

    async def get_list(self, list_id: str) -> dict:
        return await self._get(f"lists/{list_id}")  # type: ignore

    async def create_list(self, title: str) -> dict:
        return await self._post("lists", json={"title": title})  # type: ignore

    async def update_list(self, list_id: str, title: str) -> dict:
        return await self._put_json(f"lists/{list_id}", json={"title": title})  # type: ignore

    async def delete_list(self, list_id: str) -> dict:
        return await self._delete(f"lists/{list_id}")  # type: ignore

    async def get_list_accounts(self, list_id: str, **params) -> list:
        return await self._get(f"lists/{list_id}/accounts", params=params)  # type: ignore

    async def add_list_accounts(self, list_id: str, account_ids: list) -> dict:
        return await self._post(f"lists/{list_id}/accounts", json={"account_ids": account_ids})  # type: ignore

    async def remove_list_accounts(self, list_id: str, account_ids: list) -> dict:
        return await self._delete_with_body(f"lists/{list_id}/accounts", json={"account_ids": account_ids})  # type: ignore

    async def list_timeline(self, list_id: str, **params) -> list:
        clean = {k: v for k, v in params.items() if v is not None}
        return await self._get(f"timelines/list/{list_id}", params=clean)  # type: ignore

    # ── Statuses ───────────────────────────────────────────────────────
    async def get_status(self, status_id: str) -> dict:
        return await self._get(f"statuses/{status_id}")  # type: ignore

    async def create_status(self, **kwargs) -> dict:
        # None の値は除去（Mastodon が 422 を返すため）
        payload = {k: v for k, v in kwargs.items() if v is not None}
        # 空リストも除去（media_ids=[] は不要）
        payload = {k: v for k, v in payload.items() if v != []}
        return await self._post("statuses", json=payload)  # type: ignore

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

    async def _put_json(self, path: str, json: dict | None = None) -> dict:
        url = f"{self.base}/api/v1/{path}"
        logger.debug("Mastodon PUT %s", url)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(url, headers=self.headers, json=json)
        if resp.status_code == 204:
            return {}
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

    async def _delete_with_body(self, path: str, json: dict | None = None) -> dict:
        url = f"{self.base}/api/v1/{path}"
        logger.debug("Mastodon DELETE %s", url)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request("DELETE", url, headers=self.headers, json=json)
        if resp.status_code == 204:
            return {}
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

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

    # ── Reactions ─────────────────────────────────────────────────────────

    async def get_reacted_by(self, status_id: str, emoji: str) -> list:
        """
        Fedibird 拡張: 特定の絵文字でリアクションしたユーザー一覧を取得。
        GET /api/v1/statuses/{id}/reacted_by?emoji=:shortcode:
        """
        return await self._get(  # type: ignore
            f"statuses/{status_id}/reacted_by",
            params={"emoji": emoji},
        )

    # ── Reblogs ─────────────────────────────────────────────────────────

    async def get_reblogged_by(self, status_id: str) -> list:
        return await self._get(f"statuses/{status_id}/reblogged_by")  # type: ignore


    # ── Notifications ──────────────────────────────────────────────────
    async def get_notifications(self, **params) -> list:
        return await self._get("notifications", params=params)  # type: ignore

    async def clear_notifications(self) -> dict:
        return await self._post("notifications/clear")  # type: ignore

    # ── Search ─────────────────────────────────────────────────────────
    async def search(self, q: str, **params) -> dict:
        url = f"{self.base}/api/v2/search"
        search_params = {"q": q, "resolve": "false", **params}
        logger.debug("Mastodon GET %s params=%s", url, search_params)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=self.headers, params=search_params)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()  # type: ignore

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
