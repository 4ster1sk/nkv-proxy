# NKV-Proxy

Misskey クライアントからのリクエストを Mastodon API に変換するプロキシサーバーです。

```
Misskey クライアントアプリ
  │  Misskey API / WebSocket Streaming
  ▼
このプロキシ (FastAPI)
  │  Mastodon API / SSE Streaming
  ▼
上流 Mastodon インスタンス
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
git clone https://github.com/4ster1sk/nkv-proxy
cd nkv-proxy
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
| `APP_NAME` | `NKV-Proxy` | アプリ名（認証画面等に表示） |
| `INSTANCE_TITLE` | `NKV Proxy` | `/api/v1/instance` に返すインスタンス名 |
| `ENABLE_LOCAL_TIMELINE` | `auto` | `auto` / `true` / `false`。上流インスタンスの LTL 対応を自動判定 |
| `API_LIMIT_MAX` | `40` | タイムライン取得の limit 上限デフォルト値 |
| `MIAUTH_SESSION_TTL` | `600` | miAuth セッション有効期限（秒） |
| `MASTODON_OAUTH_STATE_TTL` | `300` | Mastodon OAuth state 有効期限（秒） |
| `WORKERS` | `1` | uvicorn ワーカー数（WebSocket 使用時は 1 推奨） |
| `LOG_LEVEL` | `INFO` | ログレベル（`DEBUG` / `INFO` / `WARNING` / `ERROR`） |
| `STREAMING_DEBUG` | `false` | `true` で SSE 生データ・変換前後を DEBUG 出力（`LOG_LEVEL=DEBUG` も必要） |

---

## 認証フロー

### 新規ユーザー登録

1. `http://your-proxy/register` でアカウント作成
2. ログイン後、ダッシュボードで Mastodon インスタンスと連携
3. Misskey クライアントアプリからこのプロキシに接続

### クライアントアプリからの接続設定

| 項目 | 値 |
|------|-----|
| サーバー URL | `https://your-proxy.example.com` |
| 認証方式 | miAuth（自動） |

### miAuth フロー

```
クライアントアプリ → GET /miauth/{sid}?name=...&permission=...
       ↓ ログイン済みなら権限確認画面
       ↓ 「許可する」 → OAuthToken 発行 → クライアントアプリへ
       ↓ 「拒否する」 → error=access_denied → クライアントアプリへ
```

---

## API 対応状況

### Misskey 互換 API (`/api/*`)

| エンドポイント | 対応 | 変換先 |
|--------------|------|--------|
| `POST /api/meta` | ✅ | インスタンス情報（上流転送） |
| `POST /api/stats` | ✅ | 統計情報（上流転送） |
| `POST /api/i` | ✅ | `GET /api/v1/accounts/verify_credentials` |
| `POST /api/i/update` | ✅ | `PATCH /api/v1/accounts/update_credentials` |
| `POST /api/i/notifications` | ✅ | `GET /api/v1/notifications` |
| `POST /api/notifications/mark-all-as-read` | ✅ | `DELETE /api/v1/notifications` |
| `POST /api/notes/timeline` | ✅ | `GET /api/v1/timelines/home` |
| `POST /api/notes/local-timeline` | ✅ | `GET /api/v1/timelines/public?local=true` |
| `POST /api/notes/global-timeline` | ✅ | `GET /api/v1/timelines/public` |
| `POST /api/notes/user-list-timeline` | ✅ | `GET /api/v1/timelines/list/{id}` |
| `POST /api/notes/create` | ✅ | `POST /api/v1/statuses` |
| `POST /api/notes/delete` | ✅ | `DELETE /api/v1/statuses/{id}` |
| `POST /api/notes/show` | ✅ | `GET /api/v1/statuses/{id}` |
| `POST /api/notes/renotes` | ✅ | `GET /api/v1/statuses/{id}/reblogged_by` |
| `POST /api/notes/replies` | ✅ | `GET /api/v1/statuses/{id}/context` |
| `POST /api/notes/search` | ✅ | `GET /api/v1/search?type=statuses` |
| `POST /api/notes/reactions/create` | ✅ | `POST /api/v1/statuses/{id}/favourite` |
| `POST /api/notes/reactions/delete` | ✅ | `DELETE /api/v1/statuses/{id}/unfavourite` |
| `POST /api/notes/reactions` | ✅ | `GET /api/v1/statuses/{id}/favourited_by` |
| `POST /api/notes/favorites/create` | ✅ | `POST /api/v1/statuses/{id}/bookmark` |
| `POST /api/notes/favorites/delete` | ✅ | `DELETE /api/v1/statuses/{id}/unbookmark` |
| `POST /api/emojis` | ✅ | `GET /api/v1/custom_emojis` |
| `POST /api/users/show` | ✅ | `GET /api/v1/accounts/{id}` |
| `POST /api/users/search` | ✅ | `GET /api/v1/accounts/search` |
| `POST /api/users/followers` | ✅ | `GET /api/v1/accounts/{id}/followers` |
| `POST /api/users/following` | ✅ | `GET /api/v1/accounts/{id}/following` |
| `POST /api/users/notes` | ✅ | `GET /api/v1/accounts/{id}/statuses` |
| `POST /api/users/lists/list` | ✅ | `GET /api/v1/lists` |
| `POST /api/users/lists/show` | ✅ | `GET /api/v1/lists/{id}` |
| `POST /api/users/lists/create` | ✅ | `POST /api/v1/lists` |
| `POST /api/users/lists/update` | ✅ | `PUT /api/v1/lists/{id}` |
| `POST /api/users/lists/delete` | ✅ | `DELETE /api/v1/lists/{id}` |
| `POST /api/users/lists/push` | ✅ | `POST /api/v1/lists/{id}/accounts` |
| `POST /api/users/lists/pull` | ✅ | `DELETE /api/v1/lists/{id}/accounts` |
| `POST /api/users/lists/get-memberships` | ✅ | `GET /api/v1/lists/{id}/accounts` |
| `POST /api/following/create` | ✅ | `POST /api/v1/accounts/{id}/follow` |
| `POST /api/following/delete` | ✅ | `POST /api/v1/accounts/{id}/unfollow` |
| `POST /api/blocking/create` | ✅ | `POST /api/v1/accounts/{id}/block` |
| `POST /api/blocking/delete` | ✅ | `POST /api/v1/accounts/{id}/unblock` |
| `POST /api/blocking/list` | ✅ | `GET /api/v1/blocks` |
| `POST /api/muting/create` | ✅ | `POST /api/v1/accounts/{id}/mute` |
| `POST /api/muting/delete` | ✅ | `POST /api/v1/accounts/{id}/unmute` |
| `POST /api/muting/list` | ✅ | `GET /api/v1/mutes` |
| `POST /api/admin/show-users` | ✅ | `GET /api/v1/admin/accounts`（一時無効化可） |
| `POST /api/admin/show-user` | ✅ | `GET /api/v1/admin/accounts/{id}`（一時無効化可） |
| `POST /api/admin/suspend-user` | ✅ | `POST /api/v1/admin/accounts/{id}/action`（一時無効化可） |
| `POST /api/admin/unsuspend-user` | ✅ | `POST /api/v1/admin/accounts/{id}/unsuspend`（一時無効化可） |
| `POST /api/admin/abuse-user-reports` | ✅ | `GET /api/v1/admin/reports`（一時無効化可） |
| `POST /api/antennas/*` | ❌ | 未対応（400 エラー） |
| `POST /api/channels/*` | ❌ | 未対応（400 エラー） |

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
- **2段階認証設定** — TOTP の有効化・無効化（`/settings/2fa`）
- **limit 設定** — タイムライン・通知・その他の取得件数上限をユーザーごとに設定（`/settings/limits`）

---

## 開発

```bash
# テスト実行（e2e 除く）
pytest tests/ --ignore=tests/e2e -v

# 特定テストのみ
pytest tests/test_admin_restriction.py -v
pytest tests/test_streaming.py -v
pytest tests/test_limit_settings.py -v
pytest tests/test_auth_db.py::TestMiauthConfirmFlow -v
```

### マイグレーション

```bash
# 初回・全適用
alembic upgrade head

# 差分適用
# 0002: admin_restricted + api_keys
# 0003: limit_max_tl / limit_max_notifications
# 0004: limit_max_other
alembic upgrade 0004
```

---

## ライセンス

MIT
