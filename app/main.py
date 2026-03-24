import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi import Query as WsQuery
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import misskey_compat, misskey_endpoints, nodeinfo
from app.api.v1 import accounts, misc, statuses, streaming
from app.api.v1.auth import router as auth_router
from app.core.config import settings
from app.db.database import create_tables

# ログ設定
_log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(level=_log_level)
logging.getLogger("app.services.mastodon_client").setLevel(logging.DEBUG)

logging.getLogger("app.services.streaming").setLevel(logging.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 静的ファイル（CSS/JS）
_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 認証・フロント
app.include_router(auth_router)

# Mastodon API v1
app.include_router(accounts.router)
app.include_router(statuses.router)
app.include_router(misc.router)
app.include_router(streaming.router)

# NodeInfo
app.include_router(nodeinfo.router)

# Misskey互換 API
app.include_router(misskey_compat.router)
app.include_router(misskey_endpoints.router)


@app.websocket("/streaming")
async def misskey_streaming_ws(
    websocket: WebSocket,
    i: str = WsQuery(None),
    access_token: str = WsQuery(None),
):
    """
    Misskey WebSocket ストリーミングエンドポイント。
    クライアントは ws://proxy/streaming?i=<token> で接続する。
    """
    from app.services.streaming import handle_ws_stream
    token = i or access_token or ""
    await handle_ws_stream(
        websocket, token, "user", settings.MASTODON_INSTANCE_URL
    )


@app.get("/api/v1/apps/verify_credentials")
async def verify_app():
    return {
        "name": settings.APP_NAME,
        "website": None,
        "vapid_key": None,
    }
