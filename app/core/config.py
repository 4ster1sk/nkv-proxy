from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # -----------------------------------------------------------------------
    # このプロキシ自身の設定
    # -----------------------------------------------------------------------
    # PROXY_BASE_URL: このプロキシの公開URL（必須推奨）
    # 例: https://misskey-proxy.example.com
    # 未設定の場合はリクエストの Host ヘッダーから自動推定する
    PROXY_BASE_URL: Optional[str] = None

    # アプリ名（認証画面・NodeInfo 等に表示）
    APP_NAME: str = "Misskey-Mastodon-Proxy"
    APP_DESCRIPTION: str = "Misskey API to Mastodon API proxy"
    APP_CALLBACK_URL: Optional[str] = None

    # サーバー情報（/api/v1/instance, NodeInfo で返す）
    INSTANCE_TITLE: str = "Misskey-Mastodon Bridge"
    INSTANCE_DESCRIPTION: str = "Misskey client compatible proxy for Mastodon"
    INSTANCE_VERSION: str = "4.3.0"

    # -----------------------------------------------------------------------
    # -----------------------------------------------------------------------
    # LTL (Local Timeline) 制御
    # -----------------------------------------------------------------------
    # auto:  上流インスタンスの /api/v2/instance を確認して自動判定（TTL 3時間キャッシュ）
    # true:  強制有効
    # false: 強制無効
    ENABLE_LOCAL_TIMELINE: str = "auto"

    # 上流 Mastodon インスタンス
    # -----------------------------------------------------------------------
    # MASTODON_INSTANCE_URL: ユーザーが Mastodon 連携を設定していない場合の
    # フォールバックインスタンス URL。
    # ユーザーごとの接続先は DB の users.mastodon_instance で管理される。
    MASTODON_INSTANCE_URL: str = "https://nekonoverse.org"

    # PostgreSQL DSN
    DATABASE_URL: str = "postgresql+asyncpg://proxy:proxy@postgres:5432/proxy_db"

    # miAuth セッション TTL（秒）
    MIAUTH_SESSION_TTL: int = 600

    # Mastodon OAuth 一時状態 TTL（秒）
    MASTODON_OAUTH_STATE_TTL: int = 300

    # ストリーミングタイムアウト
    STREAM_TIMEOUT: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
