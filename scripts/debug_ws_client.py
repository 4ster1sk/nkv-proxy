#!/usr/bin/env python3
"""
Misskey WebSocket デバッグクライアント
Miria と同じプロトコルで proxy に接続し、全メッセージを表示する。

Usage:
  python scripts/debug_ws_client.py <proxy_url> <access_token>
  # e.g. python scripts/debug_ws_client.py ws://localhost:8000 <token>
"""

import asyncio
import json
import sys
import uuid

import websockets


async def main(base_url: str, token: str):
    url = f"{base_url}/streaming?i={token}"
    print(f"[*] Connecting to {url}")

    async with websockets.connect(url) as ws:
        print("[*] Connected")

        # Subscribe to channels (same as Miria)
        channels = {
            "homeTimeline": str(uuid.uuid4()),
            "main": str(uuid.uuid4()),
            "globalTimeline": str(uuid.uuid4()),
            "localTimeline": str(uuid.uuid4()),
        }
        for ch_name, ch_id in channels.items():
            msg = {
                "type": "connect",
                "body": {"channel": ch_name, "id": ch_id},
            }
            await ws.send(json.dumps(msg))
            print(f"[>] subscribe: {ch_name} (id={ch_id[:8]}...)")

        print("[*] Waiting for messages... (Ctrl+C to stop)\n")

        # Also send pong in response to ping
        async def receiver():
            async for raw in ws:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    await ws.send(json.dumps({"type": "pong"}))
                    print("[<] ping -> pong")
                    continue

                if msg_type == "connected":
                    body = msg.get("body", {})
                    ch_id = body.get("id", "")
                    # Find channel name
                    ch_name = next(
                        (n for n, i in channels.items() if i == ch_id),
                        "unknown",
                    )
                    print(f"[<] connected: {ch_name}")
                    continue

                if msg_type == "channel":
                    body = msg.get("body", {})
                    ch_id = body.get("id", "")
                    event_type = body.get("type", "")
                    event_body = body.get("body", {})
                    ch_name = next(
                        (n for n, i in channels.items() if i == ch_id),
                        "unknown",
                    )

                    # Summarize the event
                    summary = ""
                    if event_type == "note":
                        user = event_body.get("user", {})
                        text = (event_body.get("text") or "")[:80]
                        summary = f"@{user.get('username', '?')}: {text}"
                    elif event_type == "notification":
                        ntype = event_body.get("type", "?")
                        user = event_body.get("user", {})
                        summary = f"{ntype} from @{user.get('username', '?')}"
                    else:
                        summary = json.dumps(event_body, ensure_ascii=False)[:120]

                    print(f"[<] {ch_name}/{event_type}: {summary}")
                    continue

                # Unknown message type
                print(f"[<] {msg_type}: {json.dumps(msg, ensure_ascii=False)[:200]}")

        try:
            await receiver()
        except websockets.ConnectionClosed as e:
            print(f"\n[!] Connection closed: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <ws://proxy_url> <access_token>")
        sys.exit(1)
    try:
        asyncio.run(main(sys.argv[1], sys.argv[2]))
    except KeyboardInterrupt:
        print("\n[*] Stopped")
