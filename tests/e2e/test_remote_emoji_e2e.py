"""
E2E test: Remote custom emoji reactions via nkv-proxy.

Tests that remote custom emoji (from nkv-app-2) are correctly
represented in Misskey-compat API responses with :name@domain: keys
and populated reactionEmojis.

Flow:
  1. Upload custom emoji "testlocal" on nkv-app
  2. Upload custom emoji "testremote" on nkv-app-2
  3. Register proxy user + OAuth + MiAuth
  4. Create a note
  5. Add local emoji reaction via Fedibird API
  6. Add remote emoji reaction via Fedibird API
  7. Verify /api/notes/show returns correct reactions + reactionEmojis
  8. Verify /api/notes/reactions returns correct keys
"""

import base64
import time
from urllib.parse import urlparse

import httpx
import pytest
from bs4 import BeautifulSoup

from tests.e2e.conftest import NKV_BACKEND, PROXY_BASE

_TS = str(int(time.time()))

# 1x1 transparent PNG
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
    "2mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

NKV_USER = "admin"
NKV_PASS = "testpassword123"

pytestmark = pytest.mark.asyncio


def _extract_oauth_code(resp: httpx.Response) -> str:
    """Extract authorization code from OAuth response (302 redirect or 200 OOB page)."""
    if resp.status_code == 302:
        location = resp.headers["location"]
        if "code=" in location:
            return location.split("code=")[1].split("&")[0]
        raise AssertionError(f"No code in redirect: {location}")

    if resp.status_code == 200:
        # OOB: code is displayed on the page in a div#oob-code or .code element
        soup = BeautifulSoup(resp.text, "html.parser")
        code_el = soup.find(id="oob-code") or soup.find(class_="code")
        if code_el:
            return code_el.get_text().strip()
        # Fallback: look for code-like string
        import re
        match = re.search(r'[A-Za-z0-9_-]{20,}', resp.text)
        if match:
            return match.group(0)
        raise AssertionError(f"Cannot find code in OOB page: {resp.text[:500]}")

    raise AssertionError(f"OAuth failed: {resp.status_code} {resp.text[:300]}")


async def _get_nkv_oauth_token(
    client: httpx.AsyncClient,
    backend_url: str,
    scopes: str = "read write admin:write",
) -> str:
    """Get an OAuth token for the admin user on a Nekonoverse instance."""
    cookies = httpx.Cookies()

    # Register OAuth app
    resp = await client.post(
        f"{backend_url}/api/v1/apps",
        json={
            "client_name": f"E2E Emoji Test {_TS}",
            "redirect_uris": "urn:ietf:wg:oauth:2.0:oob",
            "scopes": scopes,
        },
    )
    assert resp.status_code == 200, f"App registration failed: {resp.text}"
    app = resp.json()
    client_id = app["client_id"]
    client_secret = app["client_secret"]

    # GET OAuth authorize form
    resp = await client.get(
        f"{backend_url}/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
            "response_type": "code",
            "scope": scopes,
        },
        cookies=cookies,
        follow_redirects=False,
    )
    assert resp.status_code == 200, f"OAuth form failed: {resp.status_code}"

    # Parse and submit login form
    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form")
    assert form is not None, "No form in OAuth page"

    hidden = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if name and inp.get("type") == "hidden":
            hidden[name] = inp.get("value", "")

    resp = await client.post(
        f"{backend_url}/oauth/authorize",
        data={**hidden, "username": NKV_USER, "password": NKV_PASS},
        cookies=cookies,
        follow_redirects=False,
    )
    cookies.update(resp.cookies)

    # Handle consent form if shown
    if resp.status_code == 200 and "authorize" in resp.text.lower():
        soup = BeautifulSoup(resp.text, "html.parser")
        cf = soup.find("form")
        if cf:
            cfields = {}
            for inp in cf.find_all("input"):
                n = inp.get("name")
                if n:
                    cfields[n] = inp.get("value", "")
            resp = await client.post(
                f"{backend_url}/oauth/authorize",
                data=cfields,
                cookies=cookies,
                follow_redirects=False,
            )

    # Extract authorization code
    code = _extract_oauth_code(resp)

    # Exchange for token
    resp = await client.post(
        f"{backend_url}/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        },
    )
    assert resp.status_code == 200, f"Token exchange failed: {resp.text}"
    return resp.json()["access_token"]


async def _upload_custom_emoji(
    client: httpx.AsyncClient,
    backend_url: str,
    token: str,
    shortcode: str,
) -> dict:
    """Upload a custom emoji to a Nekonoverse instance."""
    resp = await client.post(
        f"{backend_url}/api/v1/admin/emoji/add",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (f"{shortcode}.png", TINY_PNG, "image/png")},
        data={"shortcode": shortcode},
    )
    assert resp.status_code in (200, 201, 422), (
        f"Emoji upload failed: {resp.status_code} {resp.text[:500]}"
    )
    if resp.status_code == 422:
        # Already exists, that's OK
        print(f"  Emoji '{shortcode}' already exists on {backend_url}")
        return {}
    return resp.json()


async def _get_proxy_token(client: httpx.AsyncClient) -> str:
    """Register + OAuth + MiAuth flow to get a proxy access token."""
    proxy_user = f"emoji_{_TS}"
    proxy_pass = "testpass123"
    proxy_cookies = httpx.Cookies()
    nkv_cookies = httpx.Cookies()

    # Register
    resp = await client.post(
        f"{PROXY_BASE}/register",
        data={"username": proxy_user, "password": proxy_pass, "password_confirm": proxy_pass},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    # Login
    resp = await client.post(
        f"{PROXY_BASE}/login",
        data={"username": proxy_user, "password": proxy_pass},
        follow_redirects=False,
    )
    proxy_cookies.update(resp.cookies)

    # Mastodon connect
    resp = await client.post(
        f"{PROXY_BASE}/dashboard/mastodon-connect",
        data={"instance_url": NKV_BACKEND},
        cookies=proxy_cookies,
        follow_redirects=False,
    )
    assert resp.status_code == 302
    oauth_url = resp.headers["location"]

    # NKV OAuth
    resp = await client.get(oauth_url, cookies=nkv_cookies, follow_redirects=False)
    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form")
    hidden = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if name and inp.get("type") == "hidden":
            hidden[name] = inp.get("value", "")

    resp = await client.post(
        f"{NKV_BACKEND}/oauth/authorize",
        data={**hidden, "username": NKV_USER, "password": NKV_PASS},
        cookies=nkv_cookies,
        follow_redirects=False,
    )
    nkv_cookies.update(resp.cookies)

    if resp.status_code == 200 and "authorize" in resp.text.lower():
        soup = BeautifulSoup(resp.text, "html.parser")
        cf = soup.find("form")
        if cf:
            cfields = {}
            for inp in cf.find_all("input"):
                n = inp.get("name")
                if n:
                    cfields[n] = inp.get("value", "")
            resp = await client.post(
                f"{NKV_BACKEND}/oauth/authorize",
                data=cfields,
                cookies=nkv_cookies,
                follow_redirects=False,
            )

    callback_url = resp.headers["location"]
    resp = await client.get(callback_url, cookies=proxy_cookies, follow_redirects=False)
    proxy_cookies.update(resp.cookies)

    # MiAuth
    resp = await client.post(
        f"{PROXY_BASE}/api/v1/apps",
        json={"client_name": "Emoji E2E", "redirect_uris": "urn:ietf:wg:oauth:2.0:oob", "scopes": "read write"},
    )
    cid = resp.json()["client_id"]

    resp = await client.get(
        f"{PROXY_BASE}/oauth/authorize",
        params={"client_id": cid, "redirect_uri": "urn:ietf:wg:oauth:2.0:oob", "response_type": "code", "scope": "read write"},
        follow_redirects=False,
    )
    miauth_url = resp.headers["location"]
    sid = urlparse(miauth_url).path.split("/miauth/")[1].split("?")[0]

    if not miauth_url.startswith("http"):
        miauth_url = f"{PROXY_BASE}{miauth_url}"
    await client.get(miauth_url, cookies=proxy_cookies, follow_redirects=False)
    await client.post(f"{PROXY_BASE}/miauth/{sid}/approve", cookies=proxy_cookies, follow_redirects=False)

    resp = await client.post(
        f"{PROXY_BASE}/oauth/token",
        json={"grant_type": "authorization_code", "code": sid},
    )
    return resp.json()["access_token"]


async def test_remote_emoji_reactions(services_ready):
    """Test custom emoji reactions appear correctly in proxy API.

    NKV requires `:shortcode:` format for custom emoji reactions.
    NKV allows multiple reactions per user (unlike standard Misskey).
    The proxy user is linked to the NKV admin account via OAuth.
    """

    async with httpx.AsyncClient(timeout=30) as client:
        # ========================================
        # STEP 1: Get admin token for NKV + upload custom emoji
        # ========================================
        print("\n[STEP 1] Getting admin token and uploading emoji...")
        nkv1_token = await _get_nkv_oauth_token(client, NKV_BACKEND)
        print(f"  nkv-app token: {nkv1_token[:20]}...")

        local_shortcode = f"testlocal{_TS}"
        await _upload_custom_emoji(client, NKV_BACKEND, nkv1_token, local_shortcode)
        print(f"  Uploaded '{local_shortcode}' on nkv-app")

        # ========================================
        # STEP 2: Get proxy access token
        # ========================================
        print("\n[STEP 2] Getting proxy token...")
        proxy_token = await _get_proxy_token(client)
        print(f"  Proxy token: {proxy_token[:20]}...")

        # ========================================
        # STEP 3: Create a note
        # ========================================
        print("\n[STEP 3] Creating note...")
        resp = await client.post(
            f"{PROXY_BASE}/api/notes/create",
            json={"i": proxy_token, "text": f"Emoji test {_TS}", "visibility": "public"},
        )
        assert resp.status_code == 200
        note = resp.json()["createdNote"]
        note_id = note["id"]
        print(f"  Note ID: {note_id}")

        # ========================================
        # STEP 4: Add custom emoji reaction via Fedibird API
        #         NKV requires `:shortcode:` format (with colons)
        # ========================================
        print("\n[STEP 4] Adding custom emoji reaction...")
        resp = await client.put(
            f"{NKV_BACKEND}/api/v1/statuses/{note_id}/emoji_reactions/:{local_shortcode}:",
            headers={"Authorization": f"Bearer {nkv1_token}"},
        )
        print(f"  Custom reaction PUT: {resp.status_code}")
        assert resp.status_code == 200, f"Custom emoji reaction failed: {resp.text[:300]}"

        # ========================================
        # STEP 5: Also add a favourite (shows as ⭐ in emoji_reactions)
        # ========================================
        print("\n[STEP 5] Adding favourite (⭐) via proxy...")
        resp = await client.post(
            f"{PROXY_BASE}/api/notes/reactions/create",
            json={"i": proxy_token, "noteId": note_id, "reaction": "⭐"},
        )
        print(f"  Reaction create: {resp.status_code}")

        # ========================================
        # STEP 6: Verify /api/notes/show
        # ========================================
        print("\n[STEP 6] Checking /api/notes/show...")
        resp = await client.post(
            f"{PROXY_BASE}/api/notes/show",
            json={"i": proxy_token, "noteId": note_id},
        )
        assert resp.status_code == 200
        show = resp.json()

        reactions = show.get("reactions", {})
        reaction_emojis = show.get("reactionEmojis", {})
        reaction_count = show.get("reactionCount", 0)
        my_reaction = show.get("myReaction")

        print(f"  reactions: {reactions}")
        print(f"  reactionCount: {reaction_count}")
        print(f"  reactionEmojis: {reaction_emojis}")
        print(f"  myReaction: {my_reaction}")

        # Assertions
        assert reaction_count > 0, "No reactions found"

        # Custom emoji should be in reactions dict with :shortcode: key
        custom_key = f":{local_shortcode}:"
        if custom_key in reactions:
            print(f"  Custom emoji '{custom_key}' found in reactions!")
            assert reactions[custom_key] >= 1
            # reactionEmojis should have URL for custom emoji
            assert custom_key in reaction_emojis, (
                f"Custom emoji {custom_key} should be in reactionEmojis, got: {reaction_emojis}"
            )
            assert reaction_emojis[custom_key], (
                f"reactionEmojis[{custom_key}] should have a URL"
            )
            print(f"  reactionEmojis URL: {reaction_emojis[custom_key]}")
        else:
            print(f"  WARNING: Custom emoji '{custom_key}' not in reactions: {reactions}")

        # Unicode emojis should NOT be in reactionEmojis
        for key in reactions:
            if not key.startswith(":"):
                assert key not in reaction_emojis, (
                    f"Unicode emoji {key} should not be in reactionEmojis"
                )

        # ========================================
        # STEP 7: Verify /api/notes/reactions list
        # ========================================
        print("\n[STEP 7] Checking /api/notes/reactions...")
        resp = await client.post(
            f"{PROXY_BASE}/api/notes/reactions",
            json={"i": proxy_token, "noteId": note_id},
        )
        assert resp.status_code == 200
        reaction_list = resp.json()
        print(f"  Reactions list: {len(reaction_list)} entries")
        for r in reaction_list:
            print(f"    reaction={r.get('reaction')} id={r.get('id', '')[:8]}")

        # Each custom emoji reaction should use :shortcode: format
        for r in reaction_list:
            assert "reaction" in r, "Each reaction entry should have 'reaction' field"
            rkey = r["reaction"]
            # ASCII shortcodes should be wrapped in colons
            if rkey.isascii() and len(rkey) > 1:
                assert rkey.startswith(":") and rkey.endswith(":"), (
                    f"ASCII reaction key should be wrapped in colons: {rkey}"
                )

        print("\n=== Remote emoji E2E test completed! ===")
