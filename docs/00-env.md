## 設定（環境変数）

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `PROXY_BASE_URL` | *(自動推定)* | このプロキシの公開URL（OAuth コールバック等に使用） |
| `MASTODON_INSTANCE_URL` | `https://nekonoverse.org` | 上流インスタンスのフォールバック URL |
| `ENABLE_LOCAL_TIMELINE` | `auto` | `auto` / `true` / `false` |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL DSN |
| `APP_NAME` | `Misskey-Mastodon-Proxy` | アプリ名 |
| `MIAUTH_SESSION_TTL` | `600` | miAuth セッション有効期限（秒） |
| `MASTODON_OAUTH_STATE_TTL` | `300` | Mastodon OAuth state 有効期限（秒） |

### ENABLE_LOCAL_TIMELINE の詳細

- `auto`: 上流インスタンスの `/api/v2/instance` を確認（TTL **3時間**キャッシュ）
- `true`: 強制有効
- `false`: 強制無効（400 LTL_DISABLED を返す）

`/api/meta` の `features.localTimeline` もこの設定に連動する。