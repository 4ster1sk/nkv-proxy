"""
上流 Mastodon インスタンスの機能キャッシュ。

ENABLE_LOCAL_TIMELINE=auto の場合に /api/v2/instance を確認して
LTL 対応有無をキャッシュする。TTL はデフォルト 3 時間。
"""
from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

# {instance_url: (fetched_at, supports_ltl)}
_cache: dict[str, tuple[float, bool]] = {}

CACHE_TTL = 60 * 60 * 3  # 3 時間


async def supports_local_timeline(instance_url: str, ttl: int = CACHE_TTL) -> bool:
    """
    上流インスタンスが LTL をサポートするか確認してキャッシュする。

    /api/v2/instance の configuration.timelines.local.enabled を参照。
    取得失敗・フィールド不明の場合は False を返す。
    """
    now = time.time()
    if instance_url in _cache:
        fetched_at, result = _cache[instance_url]
        if now - fetched_at < ttl:
            logger.debug(
                "instance_cache HIT %s → ltl=%s (age=%.0fs)",
                instance_url, result, now - fetched_at,
            )
            return result

    logger.debug("instance_cache MISS %s — fetching /api/v2/instance", instance_url)
    result = False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{instance_url}/api/v2/instance")
        if resp.status_code == 200:
            data = resp.json()
            # Mastodon 3.5+ の configuration.timelines.local.enabled
            timelines = (
                data.get("configuration", {})
                    .get("timelines", {})
                    .get("local", {})
            )
            result = bool(timelines.get("enabled", False))
    except Exception as exc:
        logger.warning("instance_cache fetch error %s: %s", instance_url, exc)

    _cache[instance_url] = (now, result)
    logger.debug("instance_cache STORE %s → ltl=%s", instance_url, result)
    return result


def invalidate(instance_url: str) -> None:
    """キャッシュを手動で無効化する（テスト用）。"""
    _cache.pop(instance_url, None)


def clear_all() -> None:
    """全キャッシュをクリアする（テスト用）。"""
    _cache.clear()
