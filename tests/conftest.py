import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import (
    crud,
    models,  # noqa: F401
)
from app.db.database import Base, get_db

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_TestSession = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)

# テスト用固定トークン
TEST_ACCESS_TOKEN = "test_access_token_fixed"
TEST_USERNAME = "testuser"
TEST_USER_ID = "user001-test-0000-0000-000000000001"


async def _override_get_db():
    async with _TestSession() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture(autouse=True)
def setup_test_db():
    async def _create():
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # テスト用ユーザーとトークンを作成
        async with _TestSession() as s:
            existing = await crud.get_user_by_username(s, TEST_USERNAME)
            if existing is None:
                user = await crud.create_user(
                    s, username=TEST_USERNAME, password="testpassword123"
                )
                # IDを固定
                user.id = TEST_USER_ID
                # mastodon_token を設定（/api/i 等のテストで必要）
                user.mastodon_token = "test_mastodon_token"
                user.mastodon_instance = "https://nekonoverse.org"
                user.mastodon_account_id = "masto_user_001"
                await s.flush()
                token = await crud.create_oauth_token(
                    s, session_id=None, app_id=None, user_id=user.id
                )
                # アクセストークンを固定値に上書き
                token.access_token = TEST_ACCESS_TOKEN
                await s.commit()

    async def _drop():
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.get_event_loop().run_until_complete(_create())
    yield
    asyncio.get_event_loop().run_until_complete(_drop())


@pytest.fixture
def client():
    from app.main import app
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {TEST_ACCESS_TOKEN}"}


# ---------------------------------------------------------------------------
# サンプルデータ
# ---------------------------------------------------------------------------

SAMPLE_USER = {
    "id": "user001",
    "username": "testuser",
    "name": "Test User",
    "host": None,
    "avatarUrl": "https://example.com/avatar.png",
    "bannerUrl": None,
    "description": "A test user",
    "isLocked": False,
    "isBot": False,
    "isAdmin": False,
    "isModerator": False,
    "followersCount": 10,
    "followingCount": 5,
    "notesCount": 100,
    "createdAt": "2023-01-01T00:00:00.000Z",
    "fields": [],
    "emojis": [],
}

SAMPLE_NOTE = {
    "id": "note001",
    "createdAt": "2023-06-01T12:00:00.000Z",
    "text": "Hello, world!",
    "cw": None,
    "visibility": "public",
    "userId": "user001",
    "user": SAMPLE_USER,
    "replyId": None,
    "renoteId": None,
    "reactions": {"❤": 3, ":awesome:": 1},
    "renoteCount": 2,
    "repliesCount": 1,
    "files": [],
    "tags": [],
    "mentions": [],
    "emojis": [],
    "lang": "ja",
    "poll": None,
}

SAMPLE_NOTIFICATION = {
    "id": "notif001",
    "createdAt": "2023-06-01T13:00:00.000Z",
    "type": "reaction",
    "userId": "user002",
    "notifier": {**SAMPLE_USER, "id": "user002", "username": "reactor"},
    "note": SAMPLE_NOTE,
    "reaction": "❤",
}


@pytest.fixture
def mock_misskey_i():
    with patch(
        "app.services.misskey_client.MisskeyClient._post", new_callable=AsyncMock
    ) as mock:
        mock.return_value = SAMPLE_USER
        yield mock
