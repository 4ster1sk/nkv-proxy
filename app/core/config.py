from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # このプロキシ自身の公開 URL
    PROXY_BASE_URL: Optional[str] = None

    # アプリ名（認証画面等に表示）
    APP_NAME: str = "Misskey-Mastodon-Proxy"
    APP_DESCRIPTION: str = "Misskey API to Mastodon API proxy"
    APP_CALLBACK_URL: Optional[str] = None

    # サーバー情報（Mastodon /api/v1/instance で返す）
    INSTANCE_TITLE: str = "Misskey-Mastodon Bridge"
    INSTANCE_DESCRIPTION: str = "Misskey client compatible proxy for Mastodon"
    INSTANCE_VERSION: str = "4.3.0"

    # 上流 Mastodon インスタンス URL
    MASTODON_INSTANCE_URL: str = "https://mastodon.social"

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
