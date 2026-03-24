# Misskey-Mastodon Proxy

Misskey クライアントからのリクエストを Mastodon API に変換するプロキシサーバーです。

```
Miria (Misskey クライアント)
  │  Misskey API / WebSocket Streaming
  ▼
このプロキシ (FastAPI)
  │  Mastodon API / SSE Streaming
  ▼
上流 Mastodon インスタンス（nekonoverse.org 等）
```

---

## 機能

- **Misskey API → Mastodon API 変換** (`/api/*`)
- **miAuth 認証フロー** (権限確認画面付き)
- **Misskey WebSocket Streaming → Mastodon SSE 変換** (`/streaming`)
- **Web ダッシュボード** (Mastodon 連携・アプリ管理・API テストフォーム)
- **管理者 API 一時無効化** (アプリごとのトグル)
- **2段階認証 (TOTP)**
- **共通 API キー** (Web UI テスト用)

---

## クイックスタート

### Docker Compose（推奨）

```bash
git clone https://github.com/yourorg/misskey-mastodon-proxy
cd misskey-mastodon-proxy
cp .env.example .env
# .env を編集（PROXY_BASE_URL, MASTODON_INSTANCE_URL）
docker compose up -d
```

ブラウザで `http://localhost:8000` にアクセスし、アカウントを登録してください。

### ローカル開発

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# DATABASE_URL を sqlite+aiosqlite:///./dev.db に変更
uvicorn app.main:app --reload
```

---

## 環境変数

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `PROXY_BASE_URL` | *(自動推定)* | このプロキシの公開URL。OAuth コールバック・NodeInfo 生成に使用 |
| `MASTODON_INSTANCE_URL` | `https://nekonoverse.org` | 上流 Mastodon のデフォルトインスタンス（ユーザー個別設定がない場合のフォールバック） |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL DSN |
| `APP_NAME` | `Misskey-Mastodon-Proxy` | アプリ名（認証画面等に表示） |
| `INSTANCE_TITLE` | `Misskey-Mastodon Bridge` | `/api/v1/instance` に返すインスタンス名 |
| `MIAUTH_SESSION_TTL` | `600` | miAuth セッション有効期限（秒） |
| `MASTODON_OAUTH_STATE_TTL` | `300` | Mastodon OAuth state 有効期限（秒） |
| `WORKERS` | `1` | uvicorn ワーカー数（WebSocket 使用時は 1 推奨） |

---

## 認証フロー

### 新規ユーザー登録

1. `http://your-proxy/register` でアカウント作成
2. ログイン後、ダッシュボードで Mastodon インスタンスと連携
3. Miria 等のクライアントからこのプロキシに接続

### Miria からの接続設定

| 項目 | 値 |
|------|-----|
| サーバー URL | `https://your-proxy.example.com` |
| 認証方式 | miAuth（自動） |

### miAuth フロー

```
Miria → GET /miauth/{sid}?name=...&permission=...
       ↓ ログイン済みなら権限確認画面
       ↓ 「許可する」 → OAuthToken 発行 → Miria へ
       ↓ 「拒否する」 → error=access_denied → Miria へ
```

---

## API 対応状況

### Misskey 互換 API (`/api/*`)

| エンドポイント | 対応 | 変換先 |
|--------------|------|--------|
| `POST /api/i` | ✅ | `GET /api/v1/accounts/verify_credentials` |
| `POST /api/i/update` | ✅ | `PATCH /api/v1/accounts/update_credentials` |
| `POST /api/notes/timeline` | ✅ | `GET /api/v1/timelines/home` |
| `POST /api/notes/local-timeline` | ✅ | `GET /api/v1/timelines/public?local=true` |
| `POST /api/notes/global-timeline` | ✅ | `GET /api/v1/timelines/public` |
| `POST /api/notes/create` | ✅ | `POST /api/v1/statuses` |
| `POST /api/notes/delete` | ✅ | `DELETE /api/v1/statuses/{id}` |
| `POST /api/notes/show` | ✅ | `GET /api/v1/statuses/{id}` |
| `POST /api/notes/reactions/create` | ✅ | `POST /api/v1/statuses/{id}/favourite` |
| `POST /api/notes/reactions/delete` | ✅ | `DELETE /api/v1/statuses/{id}/unfavourite` |
| `POST /api/notes/favorites/create` | ✅ | `POST /api/v1/statuses/{id}/bookmark` |
| `POST /api/emojis` | ✅ | `GET /api/v1/custom_emojis` |
| `POST /api/users/show` | ✅ | `GET /api/v1/accounts/{id}` |
| `POST /api/users/search` | ✅ | `GET /api/v1/accounts/search` |
| `POST /api/users/followers` | ✅ | `GET /api/v1/accounts/{id}/followers` |
| `POST /api/users/following` | ✅ | `GET /api/v1/accounts/{id}/following` |
| `POST /api/users/notes` | ✅ | `GET /api/v1/accounts/{id}/statuses` |
| `POST /api/following/create` | ✅ | `POST /api/v1/accounts/{id}/follow` |
| `POST /api/following/delete` | ✅ | `POST /api/v1/accounts/{id}/unfollow` |
| `POST /api/blocking/create` | ✅ | `POST /api/v1/accounts/{id}/block` |
| `POST /api/muting/create` | ✅ | `POST /api/v1/accounts/{id}/mute` |
| `POST /api/admin/*` | ✅ | `GET/POST /api/v1/admin/*`（一時無効化可） |

### Mastodon 互換 API (`/api/v1/*`)

標準的な Mastodon API エンドポイントは全て上流インスタンスにプロキシされます。

### WebSocket Streaming (`/streaming`)

| Misskey チャンネル | Mastodon SSE エンドポイント |
|-------------------|--------------------------|
| `homeTimeline` | `/api/v1/streaming/user` |
| `localTimeline` | `/api/v1/streaming/public/local` |
| `globalTimeline`, `hybridTimeline` | `/api/v1/streaming/public` |
| `main`, `notifications` | `/api/v1/streaming/user/notification` |

接続: `ws://your-proxy/streaming?i=<token>`

---

## ダッシュボード

`http://your-proxy/dashboard` でアクセスできます。

- **Mastodon 連携** — 任意の Mastodon インスタンスと連携
- **認証済みアプリ一覧** — 権限の確認・取消・admin API 一時無効化
- **共通 API キー** — Web UI テスト用キーの表示（👁 ボタン）・再生成
- **Misskey API テスト** — プロキシ自身に API リクエストを送信
- **Mastodon API テスト** — 上流 Mastodon に直接リクエストを送信
- **2段階認証設定** — TOTP の有効化・無効化

---

## 開発

```bash
# テスト実行
pytest tests/ -v

# 特定テストのみ
pytest tests/test_admin_restriction.py -v
pytest tests/test_streaming.py -v
pytest tests/test_auth_db.py::TestMiauthConfirmFlow -v
```

### マイグレーション

```bash
# 初回
alembic upgrade head

# 差分適用（0002: admin_restricted + api_keys）
alembic upgrade 0002
```

---

## ライセンス

MIT
