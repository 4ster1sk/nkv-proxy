"""Simulate Miria's exact API calls against nkv-proxy."""
import json
import sys

import requests

token = sys.argv[1] if len(sys.argv) > 1 else ""
base = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"

def post(path, body=None):
    if body is None:
        body = {}
    body["i"] = token
    r = requests.post(f"{base}{path}", json=body)
    return r

# 1. /api/meta
print("=== /api/meta ===")
r = post("/api/meta")
print(f"status: {r.status_code}")
meta = r.json()
print(f"version: {meta.get('version', 'MISSING')}")
print(f"uri: {meta.get('uri', 'MISSING')}")
print(f"features: {meta.get('features', 'MISSING')}")
print()

# 2. /api/i
print("=== /api/i ===")
r = post("/api/i")
print(f"status: {r.status_code}")
me = r.json()
print(f"username: {me.get('username', 'MISSING')}")
print(f"id: {me.get('id', 'MISSING')}")
print()

# 3. /api/emojis
print("=== /api/emojis ===")
r = post("/api/emojis")
print(f"status: {r.status_code}")
emojis = r.json()
if isinstance(emojis, dict):
    print(f"keys: {list(emojis.keys())}")
    if "emojis" in emojis:
        print(f"emoji count: {len(emojis['emojis'])}")
print()

# 4. /api/notes/timeline
print("=== /api/notes/timeline ===")
r = post("/api/notes/timeline", {"limit": 5})
print(f"status: {r.status_code}")
tl = r.json()
if isinstance(tl, list):
    print(f"count: {len(tl)}")
    for i, n in enumerate(tl[:3]):
        uid = n.get("user", {}).get("username", "?")
        text = (n.get("text") or "(no text)")[:60]
        vis = n.get("visibility", "?")
        renote = n.get("renoteId")
        print(f"  [{i}] @{uid}: {text} (vis={vis}, renote={bool(renote)})")
else:
    print(f"ERROR: expected list, got: {json.dumps(tl, ensure_ascii=False)[:300]}")
print()

# 5. /api/notes/create + show
print("=== /api/notes/create ===")
r = post("/api/notes/create", {"text": "Misskey.py debug test", "visibility": "public"})
print(f"status: {r.status_code}")
result = r.json()
if "createdNote" in result:
    note = result["createdNote"]
    note_id = note["id"]
    print(f"note_id: {note_id}")
    print(f"text: {note.get('text')}")

    # Verify in timeline
    print()
    print("=== /api/notes/timeline (after create) ===")
    r = post("/api/notes/timeline", {"limit": 5})
    tl = r.json()
    found = any(n.get("id") == note_id for n in tl) if isinstance(tl, list) else False
    print(f"created note in timeline: {found}")

    # Delete
    print()
    print("=== /api/notes/delete ===")
    r = post("/api/notes/delete", {"noteId": note_id})
    print(f"status: {r.status_code}")
else:
    print(f"ERROR: {json.dumps(result, ensure_ascii=False)[:300]}")
print()

# 6. /api/announcements (Miria calls this)
print("=== /api/announcements ===")
r = post("/api/announcements")
print(f"status: {r.status_code}")
print(f"body: {r.text[:200]}")

print("\n=== Done ===")
