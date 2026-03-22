from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.database import create_tables
from app.api.v1 import accounts, statuses, misc, streaming
from app.api.v1.auth import router as auth_router
from app.api import nodeinfo, misskey_compat, misskey_endpoints


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


@app.get("/api/v1/apps/verify_credentials")
async def verify_app():
    return {
        "name": settings.APP_NAME,
        "website": None,
        "vapid_key": None,
    }
