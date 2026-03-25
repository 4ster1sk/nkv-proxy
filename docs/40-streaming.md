## WebSocket Streaming の設計

```
クライアントアプリ → ws://proxy/streaming?i=<token>   (Misskey WS プロトコル)
      ↕ MisskeyStreamingProxy
上流  ← GET /api/v1/streaming/{path}     (Mastodon SSE)
```

### チャンネル → SSE パス マッピング

| Misskey チャンネル | Mastodon SSE URL |
|-------------------|----------------|
| `homeTimeline`, `main`, `notifications` | `/api/v1/streaming/user` |
| `localTimeline` | `/api/v1/streaming/public` ※Nekonoverse に /public/local はない |
| `globalTimeline`, `hybridTimeline` | `/api/v1/streaming/public` |

### イベント変換

| Mastodon SSE イベント | Misskey WS イベント |
|---------------------|------------------|
| `update` | `note`（masto_status_to_mk_note で変換） |
| `notification` (favourite) | `notification` (reaction) |
| `notification` (mention) | `notification` (reply) |
| `notification` (reblog) | `notification` (renote) |
| `notification` (follow) | `notification` (follow) |
| `delete` | `noteDeleted` |
| `status.updated` | `noteUpdated` |
| `filters_changed` | `meUpdated` |

**特徴:**
- 1接続で複数チャンネルを多重化（id で識別）
- SSE 切断時は5秒後に自動再接続
- 30秒ごとに ping（keepalive）