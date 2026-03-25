## テスト方針

### ユニットテスト

```bash
pytest tests/ --ignore=tests/e2e
```

- テスト用 DB: `sqlite+aiosqlite:///:memory:`
- `MastodonClient` は `patch("app.api.misskey_compat.MastodonClient")` でモック
- `supports_local_timeline` は `patch("app.api.misskey_compat.supports_local_timeline", new=AsyncMock(...))` でモック
- conftest のテストユーザーは `mastodon_token` / `mastodon_instance` 設定済み

### E2E テスト

```bash
docker compose -f docker-compose.e2e.yml up
```

実際の Nekonoverse インスタンスに対して miAuth フロー・絵文字リアクション等をテスト。
