## プロジェクト概要

Misskey サードパーティークライアントからのリクエストを Mastodon API に変換するプロキシサーバー。

**GitHub:** https://github.com/4ster1sk/nkv-proxy
**主要言語:** Python 3.11+
**フレームワーク:** FastAPI + SQLAlchemy (async) + PostgreSQL

---

## Claude への作業指示

### 実装前にプランを立てる

ユーザーから実装を求められた場合、**直接コードの変更を始めずに**まずプランを提示し、承認を得てから実装を開始すること。

### 実装・作業を開始する時は

実装、変更開始時にまずはissueをたてること。
実装やなにかしらのファイルを操作する場合は、必ず**作業用ブランチを作成**してから作業を開始すること。

### ブランチ運用

プッシュする際は **master ブランチに直接プッシュしない**。

### 日時フォーマット

Misskey クライアントに返す日時は必ず **`2026-03-20T10:12:58.728Z`** 形式（ミリ秒3桁 + `Z` サフィックス）にすること。
Python の `.isoformat()` はデフォルトで `+00:00` 形式になるため、以下の形式を使うこと。

```python
datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
```

### API ファイル構成

Misskey 互換エンドポイントは `app/api/mk/` 配下にドメイン別で分割されている。
新しいエンドポイントを追加する場合は対応するドメインファイルに追加すること。
`app/api/misskey_compat.py` はルーター集約のみで、実装は書かない。

| ファイル | 担当ドメイン |
|---------|------------|
| `app/api/mk/helpers.py` | 共通ヘルパー・依存関係（`_mastodon_client`, `_token` 等） |
| `app/api/mk/meta.py` | `/api/meta`, `/api/stats`, `/api/emojis`, `/api/ap/show` |
| `app/api/mk/account.py` | `/api/i/*`, `/api/notifications/*`, `/api/miauth/*` |
| `app/api/mk/notes.py` | `/api/notes/*`, `/api/users/lists/*` |
| `app/api/mk/users.py` | `/api/users/*`, `/api/following/*`, `/api/blocking/*`, `/api/muting/*` |
| `app/api/mk/admin.py` | `/api/admin/*` |
| `app/api/mk/unavailable.py` | 未対応スタブ（アンテナ・チャンネル・クリップ） |

テストのパッチパスは実際に使われているモジュールを指定すること。
例: `MastodonClient` → `app.api.mk.helpers.MastodonClient`、`httpx` → `app.api.mk.meta.httpx`

### テスト

- 新機能・バグ修正を実装したら、対応するテストを `tests/` に追加すること
- 実装後は `pytest tests/ --ignore=tests/e2e` を実行してテストが通ることを確認すること