#!/usr/bin/env python3
"""
Misskey.py を使って nkv-proxy の動作を検証するデバッグスクリプト。

Usage (Docker内から実行):
  python scripts/debug_misskey_client.py <proxy_base_url> <access_token>
  e.g. python scripts/debug_misskey_client.py http://proxy:8000 <token>
"""

import json
import sys
import time

from misskey import Misskey


def main(base_url: str, token: str):
    print(f"[*] Connecting to {base_url} with Misskey.py")
    mk = Misskey(address=base_url, i=token)

    # ── 1. /api/i (ユーザー情報) ──
    print("\n=== STEP 1: /api/i ===")
    try:
        me = mk.i()
        print(f"  username: {me.username}")
        print(f"  id: {me.id}")
        print(f"  OK")
    except Exception as e:
        print(f"  FAIL: {e}")

    # ── 2. /api/meta (サーバー情報) ──
    print("\n=== STEP 2: /api/meta ===")
    try:
        meta = mk.meta()
        print(f"  name: {meta.name}")
        print(f"  version: {meta.version}")
        print(f"  OK")
    except Exception as e:
        print(f"  FAIL: {e}")

    # ── 3. /api/notes/create (投稿) ──
    print("\n=== STEP 3: /api/notes/create ===")
    ts = int(time.time())
    note_text = f"debug test {ts}"
    try:
        result = mk.notes_create(text=note_text)
        note_id = result.created_note.id
        print(f"  note_id: {note_id}")
        print(f"  text: {result.created_note.text}")
        print(f"  OK")
    except Exception as e:
        print(f"  FAIL: {e}")
        # Try raw request for more detail
        print("  Trying raw request...")
        import requests
        resp = requests.post(
            f"{base_url}/api/notes/create",
            json={"i": token, "text": note_text},
        )
        print(f"  status: {resp.status_code}")
        print(f"  body: {resp.text[:500]}")
        note_id = None

    # ── 4. /api/notes/timeline (ホームTL) ──
    print("\n=== STEP 4: /api/notes/timeline ===")
    try:
        tl = mk.notes_timeline(limit=5)
        print(f"  count: {len(tl)}")
        for i, note in enumerate(tl):
            user = getattr(note, "user", None)
            username = getattr(user, "username", "?") if user else "?"
            text = (getattr(note, "text", None) or "")[:60]
            nid = getattr(note, "id", "?")
            print(f"  [{i}] @{username}: {text} (id={nid})")
        if note_id and any(getattr(n, "id", None) == note_id for n in tl):
            print(f"  Created note found in timeline!")
        elif note_id:
            print(f"  WARNING: Created note NOT found in timeline")
        print(f"  OK")
    except Exception as e:
        print(f"  FAIL: {e}")
        # Raw request fallback
        print("  Trying raw request...")
        import requests
        resp = requests.post(
            f"{base_url}/api/notes/timeline",
            json={"i": token, "limit": 5},
        )
        print(f"  status: {resp.status_code}")
        try:
            data = resp.json()
            if isinstance(data, list):
                print(f"  raw count: {len(data)}")
                for i, n in enumerate(data[:3]):
                    print(f"  [{i}] keys: {list(n.keys())[:10]}")
            else:
                print(f"  raw: {json.dumps(data, ensure_ascii=False)[:300]}")
        except Exception:
            print(f"  raw text: {resp.text[:300]}")

    # ── 5. /api/notes/local-timeline ──
    print("\n=== STEP 5: /api/notes/local-timeline ===")
    try:
        ltl = mk.notes_local_timeline(limit=5)
        print(f"  count: {len(ltl)}")
        for i, note in enumerate(ltl):
            user = getattr(note, "user", None)
            username = getattr(user, "username", "?") if user else "?"
            text = (getattr(note, "text", None) or "")[:60]
            print(f"  [{i}] @{username}: {text}")
        print(f"  OK")
    except Exception as e:
        print(f"  FAIL: {e}")

    # ── 6. /api/notes/show ──
    if note_id:
        print("\n=== STEP 6: /api/notes/show ===")
        try:
            note = mk.notes_show(note_id=note_id)
            print(f"  id: {note.id}")
            print(f"  text: {note.text}")
            print(f"  OK")
        except Exception as e:
            print(f"  FAIL: {e}")

    # ── 7. 投稿削除 ──
    if note_id:
        print("\n=== STEP 7: /api/notes/delete ===")
        try:
            mk.notes_delete(note_id=note_id)
            print(f"  Deleted note {note_id}")
            print(f"  OK")
        except Exception as e:
            print(f"  FAIL: {e}")

    print("\n=== Done ===")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <http://proxy_url> <access_token>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
