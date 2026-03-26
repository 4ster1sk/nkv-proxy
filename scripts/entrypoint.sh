#!/bin/sh
set -e

# PostgreSQL が接続可能になるまで待機
echo "Waiting for database..."
python - <<'EOF'
import asyncio
import os
import sys
import time

async def wait_for_db():
    from sqlalchemy.ext.asyncio import create_async_engine
    url = os.environ.get("DATABASE_URL", "")
    if not url or url.startswith("sqlite"):
        return
    engine = create_async_engine(url)
    for i in range(30):
        try:
            async with engine.connect():
                pass
            await engine.dispose()
            print(f"Database ready (attempt {i + 1})")
            return
        except Exception as e:
            if i == 29:
                print(f"Database not ready after 30 attempts: {e}", file=sys.stderr)
                sys.exit(1)
            time.sleep(2)

asyncio.run(wait_for_db())
EOF

# マイグレーションを適用
echo "Running database migrations..."
alembic upgrade head

# アプリケーションを起動
echo "Starting application..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${WORKERS:-1}" \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --log-level info
