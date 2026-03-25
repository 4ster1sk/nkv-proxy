## 認証フロー

### miAuth（サードパーティークライアント からの接続）
```
1. GET /miauth/{sid}?name=App&permission=read:account,...
   → ログイン済み: 権限確認画面（許可する / 拒否する）
   → 未ログイン:   /login?next={sid} へリダイレクト

2. POST /miauth/{sid}/approve → OAuthToken 発行 → redirect_uri?code={sid}
   POST /miauth/{sid}/deny   → セッション削除 → error=access_denied

3. POST /oauth/token {code: sid} → access_token

4. API 呼び出し: {"i": "<access_token>", ...}
```

### Mastodon 連携
- ダッシュボードでインスタンス URL を入力 → Mastodon OAuth フロー
- `users.mastodon_token` / `users.mastodon_instance` に保存
- 連携するまで Misskey API は叩けない（403 を返す）

### 共通 API キー
- `api_keys` テーブルに1ユーザー1キーを保存
- ダッシュボードの「APIテストフォーム」でのみ使用
- `_mastodon_client()` は OAuthToken と ApiKey 両方を認証として受け付ける

---

# Web ダッシュボードと権限管理

`/dashboard` でアクセス。

## Admin 権限の一時無効化

ダッシュボードの認証済みアプリ一覧で、`admin` スコープを持つトークンに対して **🔓 admin: 有効 / 🔒 admin: 無効** トグルボタンが表示される。

- `oauth_tokens.admin_restricted = True` に設定するとそのトークンからの `/api/admin/*` 呼び出しが **403** になる
- 他のエンドポイント（タイムライン等）は影響を受けない
- トークンごとに独立して制御可能

---

## Web ダッシュボード

`/dashboard` でアクセス。CSS は `app/static/css/main.css`、JS は `app/static/js/main.js`。

**主な機能:**
- Mastodon 連携（インスタンスを自由に選択可能）
- 認証済みアプリ一覧（権限折りたたみ表示・admin 制限トグル・取消）
- 共通 API キー（👁 ボタンで表示/非表示・再生成）
- Misskey API テストフォーム（共通 API キーを `i` フィールドに自動セット）
- Mastodon API テストフォーム（バックエンド経由で叩く）
- 2FA（TOTP）設定