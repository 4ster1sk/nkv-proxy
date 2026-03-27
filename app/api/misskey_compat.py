"""
Misskey-compatible API endpoints ( POST /api/... ).

ドメイン別モジュールのルーターを集約する。
各エンドポイントの実装は app/api/mk/ 配下を参照。
"""

from fastapi import APIRouter

from app.api.mk import account, admin, meta, notes, unavailable, users

router = APIRouter(prefix="/api", tags=["misskey-compat"])

router.include_router(meta.router)
router.include_router(account.router)
router.include_router(notes.router)
router.include_router(users.router)
router.include_router(admin.router)
router.include_router(unavailable.router)
