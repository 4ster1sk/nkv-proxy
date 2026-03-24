---
paths: 
  - "app/**/*.py"
  - "alembic/**/*"
  - "tests/**/*"
---
## API 変換の方針

### Misskey API → Mastodon API

| Misskey エンドポイント | 変換先 Mastodon API | 備考 |
|----------------------|-------------------|------|
| `POST /api/i` | `GET /api/v1/accounts/verify_credentials` | `masto_to_misskey_user_detailed(is_me=True)` |
| `POST /api/notes/timeline` | `GET /api/v1/timelines/home` | |
| `POST /api/notes/local-timeline` | `GET /api/v1/timelines/public?local=true` | ENABLE_LOCAL_TIMELINE で制御 |
| `POST /api/notes/global-timeline` | `GET /api/v1/timelines/public` | |
| `POST /api/notes/create` | `POST /api/v1/statuses` | None 値は除去してから送信 |
| `POST /api/notes/reactions/create` | `PUT /api/v1/statuses/{id}/emoji_reactions/{emoji}` | Fedibird 拡張。失敗時は favourite にフォールバック |
| `POST /api/notes/reactions` | `GET /api/v1/statuses/{id}/reacted_by?emoji=:emoji:` | reaction 指定なしは get_status の emoji_reactions から構築 |
| `POST /api/notes/renotes` | `GET /api/v1/statuses/{id}/reblogged_by` | `mk_renote_stub()` でスタブ生成 |
| `POST /api/emojis` | `GET /api/v1/custom_emojis` | |
| `POST /api/users/following` | `GET /api/v1/accounts/{id}/following` | `_mk_follow_relationship()` で createdAt/followerId 等を補完 |
| `POST /api/admin/*` | `GET/POST /api/v1/admin/*` | `admin_restricted` フラグで一時無効化可能 |

### ページネーション変換

Misskey → Mastodon のパラメータ変換:

| Misskey | Mastodon | 意味 |
|---------|----------|------|
| `sinceId` | `min_id` | これより新しい投稿 |
| `untilId` | `max_id` | これより古い投稿 |

**None の場合はパラメータ自体を送らない**（Mastodon が 422 を返すため）。

---

## データ変換の設計

### UserLite vs UserDetailed

- **`masto_to_misskey_user_lite(masto)`** — ノートに埋め込む軽量版。`id`, `username`, `avatarUrl`, `host`, `isBot`, `emojis`, `onlineStatus` 等
- **`masto_to_misskey_user_detailed(masto, db_user, is_me)`** — `/api/i`, `/api/users/show` 用の完全版。`is_me=True` で `/api/i` 専用フィールド（`policies`, `hasUnread*` 等）も含める

### リアクションキーの構築 (`_build_reaction_key`)

Fedibird の `emoji_reactions` エントリから Misskey 形式のキーを生成:

```
Unicode 絵文字:       "❤"        → "❤"
ローカルカスタム絵文字: "claude"   → ":claude:"
リモートカスタム絵文字: "awesome" + domain="remote.host" → ":awesome@remote.host:"
既に :...: 形式:      ":claude:" → ":claude:" (そのまま)
```

Mastodon の `emoji_reactions[].name` にコロンが含まれている場合は `.strip(":")` してから処理する。

### HTML → プレーンテキスト変換 (`html_to_text`)

Mastodon の `note`（description）は HTML で来るため変換が必要:
- `<br>`, `<p>` → 改行
- `<img alt=":claude:">` → `:claude:`（Mastodon のカスタム絵文字表現）
- その他タグは除去

### Renote スタブ (`mk_renote_stub`)

`reblogged_by` はアカウント一覧しか返さないため、最小限の Renote オブジェクトをスタブとして生成。`id` は `(account_id, original_note_id)` の UUIDv5 で決定論的に生成。
