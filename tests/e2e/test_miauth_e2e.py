"""
E2E test: Full MiAuth flow via nkv-proxy against real Nekonoverse.

All services run inside Docker on the same network, so URLs use
docker service names directly (no URL translation needed).

Flow:
  1. Register user on proxy
  2. Login to proxy
  3. Connect Mastodon (Nekonoverse) via OAuth
  4. MiAuth flow (simulate Misskey client)
  5. POST /api/i to verify user info
  6. Create note and verify timeline retrieval
"""

import time
from urllib.parse import urlparse

import httpx
import pytest
from bs4 import BeautifulSoup

from tests.e2e.conftest import NKV_BACKEND, PROXY_BASE

# Use timestamp suffix so the test is re-runnable without DB reset
_TS = str(int(time.time()))
PROXY_USER = f"e2e_{_TS}"
PROXY_PASS = "e2epassword123"
NKV_USER = "admin"
NKV_PASS = "testpassword123"

pytestmark = pytest.mark.asyncio


async def test_full_miauth_flow(services_ready):
    """Test complete flow: registration -> OAuth -> MiAuth -> /api/i -> notes."""

    proxy_cookies = httpx.Cookies()
    nkv_cookies = httpx.Cookies()

    async with httpx.AsyncClient(timeout=30) as client:
        # ==================================================
        # STEP 1: Register user on proxy
        # ==================================================
        resp = await client.post(
            f"{PROXY_BASE}/register",
            data={
                "username": PROXY_USER,
                "password": PROXY_PASS,
                "password_confirm": PROXY_PASS,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, f"Register failed: {resp.status_code} {resp.text}"
        assert "/login" in resp.headers["location"]
        print(f"[STEP 1] Registered user '{PROXY_USER}' on proxy")

        # ==================================================
        # STEP 2: Login to proxy
        # ==================================================
        resp = await client.post(
            f"{PROXY_BASE}/login",
            data={"username": PROXY_USER, "password": PROXY_PASS},
            follow_redirects=False,
        )
        assert resp.status_code == 302, f"Login failed: {resp.status_code}"
        proxy_cookies.update(resp.cookies)
        assert "proxy_session" in proxy_cookies, (
            f"No session cookie. Cookies: {dict(resp.cookies)}"
        )
        print("[STEP 2] Logged in to proxy, got session cookie")

        # ==================================================
        # STEP 3: Mastodon (Nekonoverse) OAuth connection
        # ==================================================

        # 3a. Initiate Mastodon connect
        #     The proxy will register an OAuth app on nkv-app and redirect us
        #     to nkv-app's /oauth/authorize.  Since MASTODON_INSTANCE_URL and
        #     PROXY_BASE_URL both use docker service names, all URLs are
        #     reachable from inside the docker network.
        resp = await client.post(
            f"{PROXY_BASE}/dashboard/mastodon-connect",
            data={"instance_url": NKV_BACKEND},
            cookies=proxy_cookies,
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            f"mastodon-connect failed: {resp.status_code} {resp.text}"
        )
        oauth_authorize_url = resp.headers["location"]
        assert "oauth/authorize" in oauth_authorize_url, (
            f"Unexpected redirect: {oauth_authorize_url}"
        )
        print(f"[STEP 3a] Redirect to OAuth: {oauth_authorize_url[:100]}...")

        # 3b. GET the OAuth login form on Nekonoverse
        resp = await client.get(
            oauth_authorize_url,
            cookies=nkv_cookies,
            follow_redirects=False,
        )
        assert resp.status_code == 200, f"OAuth form failed: {resp.status_code}"
        print("[STEP 3b] Got Nekonoverse OAuth login form")

        # 3c. Parse hidden fields from the login form
        soup = BeautifulSoup(resp.text, "html.parser")
        form = soup.find("form")
        assert form is not None, "No form found in OAuth page"

        hidden_fields = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name and inp.get("type") == "hidden":
                hidden_fields[name] = inp.get("value", "")

        print(f"[STEP 3c] Hidden fields: {list(hidden_fields.keys())}")

        # Submit login (Nekonoverse issues authorization code directly)
        form_data = {
            **hidden_fields,
            "username": NKV_USER,
            "password": NKV_PASS,
        }
        resp = await client.post(
            f"{NKV_BACKEND}/oauth/authorize",
            data=form_data,
            cookies=nkv_cookies,
            follow_redirects=False,
        )
        nkv_cookies.update(resp.cookies)

        # If consent form is shown (logged-in user), submit it
        if resp.status_code == 200 and "authorize" in resp.text.lower():
            print("[STEP 3c] Got consent form, submitting approval...")
            soup = BeautifulSoup(resp.text, "html.parser")
            consent_form = soup.find("form")
            if consent_form:
                consent_fields = {}
                for inp in consent_form.find_all("input"):
                    name = inp.get("name")
                    if name:
                        consent_fields[name] = inp.get("value", "")
                resp = await client.post(
                    f"{NKV_BACKEND}/oauth/authorize",
                    data=consent_fields,
                    cookies=nkv_cookies,
                    follow_redirects=False,
                )

        assert resp.status_code == 302, (
            f"OAuth authorize failed: {resp.status_code} {resp.text[:300]}"
        )
        callback_url = resp.headers["location"]
        assert "auth/mastodon/callback" in callback_url, (
            f"Unexpected callback: {callback_url}"
        )
        assert "code=" in callback_url, f"No code in callback: {callback_url}"
        print("[STEP 3c] Authorization code received")

        # 3d. Follow callback redirect to proxy
        resp = await client.get(
            callback_url,
            cookies=proxy_cookies,
            follow_redirects=False,
        )
        proxy_cookies.update(resp.cookies)
        assert resp.status_code == 302, (
            f"Callback failed: {resp.status_code} {resp.text[:300]}"
        )
        assert "/dashboard" in resp.headers["location"], (
            f"Unexpected redirect after callback: {resp.headers['location']}"
        )
        print("[STEP 3d] Mastodon OAuth complete")

        # ==================================================
        # STEP 4: MiAuth flow (simulate Misskey client)
        # ==================================================

        # 4a. Register app on proxy
        resp = await client.post(
            f"{PROXY_BASE}/api/v1/apps",
            json={
                "client_name": "E2E Test Client",
                "redirect_uris": "urn:ietf:wg:oauth:2.0:oob",
                "scopes": "read write follow push",
                "website": "https://test.example.com",
            },
        )
        assert resp.status_code == 200, (
            f"App registration failed: {resp.status_code} {resp.text}"
        )
        app_data = resp.json()
        client_id = app_data["client_id"]
        assert client_id.startswith("proxy_")
        print(f"[STEP 4a] Registered app: client_id={client_id}")

        # 4b. GET /oauth/authorize -> redirect to /miauth/{sid}
        resp = await client.get(
            f"{PROXY_BASE}/oauth/authorize",
            params={
                "client_id": client_id,
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                "response_type": "code",
                "scope": "read write follow push",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, f"OAuth authorize failed: {resp.status_code}"
        miauth_url = resp.headers["location"]
        assert "/miauth/" in miauth_url, f"Expected miAuth redirect: {miauth_url}"

        # Extract session_id from miauth URL path
        path_parts = urlparse(miauth_url).path.split("/miauth/")
        session_id = path_parts[1].split("?")[0] if len(path_parts) > 1 else ""
        assert session_id, f"Could not extract session_id from {miauth_url}"
        print(f"[STEP 4b] MiAuth session: {session_id}")

        # 4c. GET /miauth/{sid} (shows permission confirmation)
        if not miauth_url.startswith("http"):
            miauth_url = f"{PROXY_BASE}{miauth_url}"
        resp = await client.get(
            miauth_url,
            cookies=proxy_cookies,
            follow_redirects=False,
        )
        assert resp.status_code == 200, f"MiAuth page failed: {resp.status_code}"
        print("[STEP 4c] Got MiAuth permission page")

        # 4d. POST /miauth/{sid}/approve
        resp = await client.post(
            f"{PROXY_BASE}/miauth/{session_id}/approve",
            cookies=proxy_cookies,
            follow_redirects=False,
        )
        assert resp.status_code == 200, (
            f"MiAuth approve failed: {resp.status_code} {resp.text[:300]}"
        )
        print("[STEP 4d] MiAuth approved")

        # 4e. Exchange code for access_token
        resp = await client.post(
            f"{PROXY_BASE}/oauth/token",
            json={
                "grant_type": "authorization_code",
                "code": session_id,
            },
        )
        assert resp.status_code == 200, (
            f"Token exchange failed: {resp.status_code} {resp.text}"
        )
        token_data = resp.json()
        access_token = token_data.get("access_token")
        assert access_token, f"No access_token in response: {token_data}"
        print(f"[STEP 4e] Got access token: {access_token[:20]}...")

        # ==================================================
        # STEP 5: Verify /api/i with the token
        # ==================================================
        resp = await client.post(
            f"{PROXY_BASE}/api/i",
            json={"i": access_token},
        )
        assert resp.status_code == 200, (
            f"/api/i failed: {resp.status_code} {resp.text[:300]}"
        )
        user_info = resp.json()
        assert "username" in user_info, (
            f"No username in response: {list(user_info.keys())}"
        )
        print(f"[STEP 5] /api/i success: username={user_info.get('username')}")

        # ==================================================
        # STEP 5b: Verify /api/meta features
        # ==================================================
        resp = await client.post(
            f"{PROXY_BASE}/api/meta",
            json={"i": access_token},
        )
        assert resp.status_code == 200, (
            f"/api/meta failed: {resp.status_code} {resp.text[:300]}"
        )
        meta = resp.json()
        features = meta.get("features", {})
        assert features.get("localTimeline") is True, (
            f"localTimeline should be True: {features}"
        )
        assert features.get("globalTimeline") is True, (
            f"globalTimeline should be True: {features}"
        )
        assert features.get("miauth") is True, (
            f"miauth should be True: {features}"
        )
        print(f"[STEP 5b] /api/meta features OK: localTL={features['localTimeline']}, globalTL={features['globalTimeline']}")

        # ==================================================
        # STEP 6: Create a note via /api/notes/create
        # ==================================================
        note_text = f"E2E test note {_TS}"
        resp = await client.post(
            f"{PROXY_BASE}/api/notes/create",
            json={"i": access_token, "text": note_text, "visibility": "public"},
        )
        assert resp.status_code == 200, (
            f"/api/notes/create failed: {resp.status_code} {resp.text[:300]}"
        )
        created = resp.json()
        assert "createdNote" in created, (
            f"No createdNote in response: {list(created.keys())}"
        )
        note = created["createdNote"]
        note_id = note["id"]
        assert note["text"] == note_text, (
            f"Note text mismatch: expected {note_text!r}, got {note['text']!r}"
        )
        print(f"[STEP 6] Created note: id={note_id}, text={note_text!r}")

        # ==================================================
        # STEP 7: Retrieve timeline and verify the note
        # ==================================================
        resp = await client.post(
            f"{PROXY_BASE}/api/notes/timeline",
            json={"i": access_token, "limit": 10},
        )
        assert resp.status_code == 200, (
            f"/api/notes/timeline failed: {resp.status_code} {resp.text[:300]}"
        )
        timeline = resp.json()
        assert isinstance(timeline, list), (
            f"Expected list, got {type(timeline).__name__}"
        )
        assert len(timeline) > 0, "Timeline is empty"
        found = any(n["id"] == note_id for n in timeline)
        assert found, (
            f"Created note {note_id} not found in timeline. "
            f"Timeline IDs: {[n['id'] for n in timeline]}"
        )
        print(f"[STEP 7] Timeline has {len(timeline)} notes, created note found")
        print("\n=== E2E MiAuth + Timeline flow completed successfully! ===")
