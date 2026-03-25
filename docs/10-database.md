## DB テーブル設計

| テーブル | 用途 |
|---------|------|
| `users` | プロキシユーザー。`mastodon_token` / `mastodon_instance` でユーザーごとの上流接続先を管理 |
| `registered_apps` | Misskey クライアントのアプリ登録（client_id / client_secret 発行） |
| `miauth_sessions` | miAuth 認可フローの一時セッション |
| `oauth_tokens` | 発行済みアクセストークン。`admin_restricted` フラグあり |
| `mastodon_apps` | 上流 Mastodon インスタンスの OAuth アプリ登録キャッシュ |
| `mastodon_oauth_states` | Mastodon OAuth CSRF 防止用一時状態 |
| `api_keys` | Web UI テスト用の共通 API キー（ユーザーごと1件） |

## マイグレーション
- `0001_initial.py` — 全テーブル作成
- `0002_add_admin_restriction.py` — `oauth_tokens.admin_restricted` + `api_keys` テーブル追加