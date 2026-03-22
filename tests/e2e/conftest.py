"""
E2E test fixtures for nkv-proxy + Nekonoverse integration.
All services run inside Docker on the same network.
"""

import asyncio

import httpx
import pytest_asyncio

# All URLs are docker-internal service names
PROXY_BASE = "http://proxy:8000"
NKV_BACKEND = "http://nkv-app:8000"


async def wait_for_healthy(url: str, timeout: float = 120, interval: float = 2):
    """Poll a health endpoint until it responds 200 or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                resp = await client.get(url, timeout=5)
                if resp.status_code == 200:
                    return
            except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
                pass
            await asyncio.sleep(interval)
    raise TimeoutError(f"Service at {url} did not become healthy within {timeout}s")


@pytest_asyncio.fixture(scope="session")
async def services_ready():
    """Wait for both proxy and nekonoverse to be healthy."""
    await asyncio.gather(
        wait_for_healthy(f"{PROXY_BASE}/api/v1/streaming/health"),
        wait_for_healthy(f"{NKV_BACKEND}/api/v1/health"),
    )
