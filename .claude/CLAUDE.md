## プロジェクト概要

Misskey サードパーティークライアントからのリクエストを Mastodon API に変換するプロキシサーバー。

```
Misskey サードパーティークライアント
  │  Misskey API / WebSocket Streaming
  ▼
nkv-proxy (FastAPI)
  │  Mastodon API / SSE Streaming
  ▼
上流 Mastodon インスタンス（Nekonoverse 等）
```

**GitHub:** https://github.com/4ster1sk/nkv-proxy
**主要言語:** Python 3.11+
**フレームワーク:** FastAPI + SQLAlchemy (async) + PostgreSQL

---

## Claude への作業指示

### 実装前にプランを立てる

ユーザーから実装を求められた場合、**直接コードの変更を始めずに**まずプランを提示し、承認を得てから実装を開始すること。

### ブランチ運用

GitHub へプッシュする際は **master ブランチに直接プッシュしない**。
必ず作業用ブランチを作成してからプッシュすること。