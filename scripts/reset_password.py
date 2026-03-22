#!/usr/bin/env python3
"""
パスワードリセット CLI。Docker コンテナ内で実行する。

Usage:
  docker exec misskey-mastodon-proxy python scripts/reset_password.py <username> [new_password]

  new_password を省略するとランダム生成して表示する。
"""

import asyncio
import secrets
import string
import sys

import bcrypt
from sqlalchemy import select

from app.db.database import AsyncSessionLocal
from app.db.models import User


def generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def reset_password(username: str, new_password: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()
        if not user:
            print(f"Error: user '{username}' not found")
            sys.exit(1)

        user.password_hash = bcrypt.hashpw(
            new_password.encode(), bcrypt.gensalt()
        ).decode()
        await session.commit()
        print(f"Password reset for '{username}': {new_password}")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <username> [new_password]")
        sys.exit(1)
    username = sys.argv[1]
    new_password = sys.argv[2] if len(sys.argv) >= 3 else generate_password()
    asyncio.run(reset_password(username, new_password))


if __name__ == "__main__":
    main()
