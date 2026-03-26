"""limit クランプユーティリティ。

各カテゴリごとのクランプ関数を一元管理する。
ユーザー設定が未設定 (None) の場合はグローバルデフォルト (API_LIMIT_MAX) を使用。
"""

from app.core.config import settings
from app.db.models import User


def clamp_tl(limit: int, user: User) -> int:
    """タイムライン系 limit をユーザー設定上限でクランプする。"""
    return min(limit, user.limit_max_tl or settings.API_LIMIT_MAX)


def clamp_notifications(limit: int, user: User) -> int:
    """通知系 limit をユーザー設定上限でクランプする。"""
    return min(limit, user.limit_max_notifications or settings.API_LIMIT_MAX)


def clamp_other(limit: int, user: User) -> int:
    """その他系 limit をユーザー設定上限でクランプする。"""
    return min(limit, user.limit_max_other or settings.API_LIMIT_MAX)
