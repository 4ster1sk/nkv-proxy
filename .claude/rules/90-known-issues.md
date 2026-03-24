## 既知の制限・今後の課題

- **`notes/renotes`**: `reblogged_by` の結果からスタブを生成しているため、実際のリノートノートの内容（テキスト等）は取得できない。`get_context` の descendants から取得する代替実装がコメントアウトで用意されている
- **Streaming の通知分離**: Nekonoverse には `/streaming/user/notification` が存在しないため、`main` / `notifications` チャンネルも `/streaming/user` に統一している（HTL と通知が同一ストリームになる）
- **`notes/search`**: Mastodon の全文検索は Elasticsearch 等が必要なため、インスタンスによっては空配列が返る
- **`messaging` / `drive`** チャンネル: Mastodon に対応するものがないため空ストリームとして扱う
- **`pinnedNotes`**: Mastodon の `/api/v1/accounts/{id}/statuses?pinned=true` で取得可能だが未実装（空配列を返す）
