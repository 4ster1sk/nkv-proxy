## ディレクトリ構成

```
app/
├── main.py                  # FastAPI アプリ・WebSocket /streaming エンドポイント
├── core/
│   ├── config.py            # Settings (pydantic-settings)
│   └── auth.py              # Bearer トークン検証
├── api/
│   ├── misskey_compat.py    # POST /api/* (Misskey 互換エンドポイント群)
│   ├── misskey_endpoints.py # POST /api/meta, /api/endpoint 等
│   ├── nodeinfo.py          # GET /.well-known/nodeinfo
│   └── v1/
│       ├── auth.py          # Web UI: 登録・ログイン・ダッシュボード・miAuth
│       ├── accounts.py      # GET/POST /api/v1/accounts/*
│       ├── statuses.py      # GET /api/v1/timelines/*
│       ├── misc.py          # GET /api/v1/instance 等
│       └── streaming.py     # GET /api/v1/streaming (SSE)
├── db/
│   ├── models.py            # ORM モデル
│   ├── crud.py              # DB 操作関数
│   └── database.py          # engine / session
└── services/
    ├── mastodon_client.py   # 上流 Mastodon API クライアント
    ├── user_converter.py    # Mastodon account → Misskey User 変換
    ├── note_converter.py    # Mastodon status → Misskey Note 変換
    ├── converter.py         # Misskey → Mastodon 変換（旧）
    ├── streaming.py         # MisskeyStreamingProxy (WS → SSE 変換)
    ├── instance_cache.py    # 上流インスタンス機能キャッシュ（TTL 3時間）
    └── misskey_client.py    # 旧 MisskeyClient（互換のため残存）
tests/
├── conftest.py
├── test_misskey_compat.py
├── test_auth_db.py
├── test_admin_restriction.py
├── test_streaming.py
└── e2e/                     # 実環境 E2E テスト（Nekonoverse 必要）
scripts/
├── debug_miria_sim.py       # Miria が叩く API を手動シミュレート
├── debug_ws_client.py       # WebSocket デバッグクライアント
├── debug_misskey_client.py
├── reset_password.py        # ユーザーパスワードリセット
└── test_reactions.py        # リアクション動作確認
```