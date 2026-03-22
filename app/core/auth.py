"""
認証依存性。

Bearer トークン → OAuthToken → User の順で DB を引く。
上流 Mastodon への転送時は User.mastodon_token を使う。
"""

from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db import crud
from app.db.models import User, OAuthToken

bearer_scheme = HTTPBearer(auto_error=False)


async def get_token_and_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> tuple[OAuthToken, User]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    result = await crud.get_token_with_user(db, credentials.credentials)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked token")
    token, user = result
    try:
        await crud.touch_token(db, credentials.credentials)
    except Exception:
        pass
    return token, user


async def get_current_user(
    token_user: tuple[OAuthToken, User] = Depends(get_token_and_user),
) -> User:
    return token_user[1]


async def get_mastodon_token(
    token_user: tuple[OAuthToken, User] = Depends(get_token_and_user),
) -> str:
    """
    上流 Mastodon API への転送に使うトークンを返す。
    User.mastodon_token が設定されていればそれを使う。
    未設定の場合はダミーを返す（API は空レスポンスを返す）。
    """
    _, user = token_user
    return user.mastodon_token or ""
