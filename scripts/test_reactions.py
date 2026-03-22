"""E2E test: emoji reaction flow."""
import json
import time
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

PROXY = "http://proxy:8000"
NKV = "http://nkv-app:8000"
TS = str(int(time.time()))


def main():
    client = httpx.Client(timeout=30)
    cookies = httpx.Cookies()
    nkv_cookies = httpx.Cookies()

    user = f"rxn_{TS}"
    pwd = "testpass123"

    # Register
    r = client.post(f"{PROXY}/register", data={"username": user, "password": pwd, "password_confirm": pwd}, follow_redirects=False)
    print(f"Register: {r.status_code}")

    # Login
    r = client.post(f"{PROXY}/login", data={"username": user, "password": pwd}, follow_redirects=False)
    print(f"Login: {r.status_code}")
    cookies.update(r.cookies)

    # Mastodon connect
    r = client.post(f"{PROXY}/dashboard/mastodon-connect", data={"instance_url": NKV}, cookies=cookies, follow_redirects=False)
    print(f"Mastodon connect: {r.status_code}")
    oauth_url = r.headers.get("location", "")
    print(f"  OAuth URL: {oauth_url[:100]}")

    # Get OAuth form
    r = client.get(oauth_url, cookies=nkv_cookies, follow_redirects=False)
    print(f"OAuth form: {r.status_code}")

    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form")
    hidden = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if name and inp.get("type") == "hidden":
            hidden[name] = inp.get("value", "")

    form_data = {**hidden, "username": "admin", "password": "testpassword123"}
    r = client.post(f"{NKV}/oauth/authorize", data=form_data, cookies=nkv_cookies, follow_redirects=False)
    nkv_cookies.update(r.cookies)

    if r.status_code == 200 and "authorize" in r.text.lower():
        soup2 = BeautifulSoup(r.text, "html.parser")
        cf = soup2.find("form")
        if cf:
            cfields = {}
            for inp in cf.find_all("input"):
                n = inp.get("name")
                if n:
                    cfields[n] = inp.get("value", "")
            r = client.post(f"{NKV}/oauth/authorize", data=cfields, cookies=nkv_cookies, follow_redirects=False)

    callback_url = r.headers.get("location", "")
    print(f"Callback URL: {callback_url[:100]}")
    r = client.get(callback_url, cookies=cookies, follow_redirects=False)
    cookies.update(r.cookies)
    print(f"OAuth callback: {r.status_code}")

    # MiAuth
    r = client.post(f"{PROXY}/api/v1/apps", json={"client_name": "RXN", "redirect_uris": "urn:ietf:wg:oauth:2.0:oob", "scopes": "read write"})
    cid = r.json()["client_id"]
    r = client.get(f"{PROXY}/oauth/authorize", params={"client_id": cid, "redirect_uri": "urn:ietf:wg:oauth:2.0:oob", "response_type": "code", "scope": "read write"}, follow_redirects=False)
    miauth_url = r.headers["location"]
    sid = urlparse(miauth_url).path.split("/miauth/")[1].split("?")[0]
    if not miauth_url.startswith("http"):
        miauth_url = f"{PROXY}{miauth_url}"
    r = client.get(miauth_url, cookies=cookies, follow_redirects=False)
    r = client.post(f"{PROXY}/miauth/{sid}/approve", cookies=cookies, follow_redirects=False)
    r = client.post(f"{PROXY}/oauth/token", json={"grant_type": "authorization_code", "code": sid})
    token = r.json()["access_token"]
    print(f"Token: {token[:20]}...")

    # Create note
    r = client.post(f"{PROXY}/api/notes/create", json={"i": token, "text": f"Reaction test {TS}", "visibility": "public"})
    note = r.json()["createdNote"]
    note_id = note["id"]
    print(f"\n=== Created note: {note_id} ===")
    print(f"  reactions: {note.get('reactions', {})}")
    print(f"  reactionCount: {note.get('reactionCount', 0)}")

    # Add ❤ reaction
    print("\n--- POST /api/notes/reactions/create (❤) ---")
    r = client.post(f"{PROXY}/api/notes/reactions/create", json={"i": token, "noteId": note_id, "reaction": "❤"})
    print(f"  Status: {r.status_code}")
    print(f"  Response: {json.dumps(r.json(), ensure_ascii=False)[:500]}")

    # Show note after reaction
    print("\n--- POST /api/notes/show (after ❤) ---")
    r = client.post(f"{PROXY}/api/notes/show", json={"i": token, "noteId": note_id})
    print(f"  Status: {r.status_code}")
    show = r.json()
    print(f"  reactions: {show.get('reactions', {})}")
    print(f"  reactionCount: {show.get('reactionCount', 0)}")
    print(f"  myReaction: {show.get('myReaction')}")

    # Raw Mastodon status from NKV directly
    print("\n--- Direct NKV: GET /api/v1/statuses/{id} ---")
    # We need the Mastodon token. Get it by checking proxy DB.
    # Instead, use the proxy's Mastodon API pass-through
    r = client.get(f"{PROXY}/api/v1/statuses/{note_id}", headers={"Authorization": f"Bearer {token}"})
    print(f"  Proxy Mastodon API status: {r.status_code}")
    if r.status_code == 200:
        st = r.json()
        print(f"  favourites_count: {st.get('favourites_count')}")
        print(f"  favourited: {st.get('favourited')}")
        print(f"  emoji_reactions: {json.dumps(st.get('emoji_reactions', []), ensure_ascii=False)}")
    else:
        print(f"  Error: {r.text[:300]}")

    # Add 👍 reaction
    print("\n--- POST /api/notes/reactions/create (👍) ---")
    r = client.post(f"{PROXY}/api/notes/reactions/create", json={"i": token, "noteId": note_id, "reaction": "👍"})
    print(f"  Status: {r.status_code}")
    resp = r.json()
    print(f"  Response reactions: {resp.get('reactions', {})}")
    print(f"  Response reactionCount: {resp.get('reactionCount', 0)}")

    # Show note again
    print("\n--- POST /api/notes/show (after 👍) ---")
    r = client.post(f"{PROXY}/api/notes/show", json={"i": token, "noteId": note_id})
    show2 = r.json()
    print(f"  reactions: {show2.get('reactions', {})}")
    print(f"  reactionCount: {show2.get('reactionCount', 0)}")
    print(f"  myReaction: {show2.get('myReaction')}")

    # List reactions
    print("\n--- POST /api/notes/reactions ---")
    r = client.post(f"{PROXY}/api/notes/reactions", json={"i": token, "noteId": note_id})
    print(f"  Status: {r.status_code}")
    print(f"  Response: {json.dumps(r.json(), ensure_ascii=False)[:500]}")

    # Timeline check
    print("\n--- POST /api/notes/timeline ---")
    r = client.post(f"{PROXY}/api/notes/timeline", json={"i": token, "limit": 3})
    tl = r.json()
    for n in tl[:3]:
        print(f"  [{n['id'][:8]}] text={n.get('text', '')[:30]} reactions={n.get('reactions', {})} count={n.get('reactionCount', 0)}")

    # Delete reaction
    print("\n--- POST /api/notes/reactions/delete ---")
    r = client.post(f"{PROXY}/api/notes/reactions/delete", json={"i": token, "noteId": note_id})
    print(f"  Status: {r.status_code}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
