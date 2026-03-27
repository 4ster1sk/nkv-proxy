# ============================================================
# Stage 1: builder — 依存パッケージのインストール
# ============================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# システム依存（cryptography のビルドに必要）
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ============================================================
# Stage 2: runtime — 軽量な実行イメージ
# ============================================================
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="NKV-Proxy" \
      org.opencontainers.image.description="Mastodon API compatible proxy for Misskey" \
      org.opencontainers.image.source="https://github.com/4ster1sk/nkv-proxy"

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 非rootユーザーで実行（セキュリティ）
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# builderステージからパッケージだけコピー
COPY --from=builder /install /usr/local

# アプリケーションコードのみコピー
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY scripts/ ./scripts/

# entrypoint に実行権限を付与
RUN chmod +x ./scripts/entrypoint.sh

# 所有権を非rootユーザーに移す
RUN chown -R appuser:appuser /app

USER appuser

# ============================================================
# 環境変数
# ============================================================
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    APP_NAME="NKV-Proxy" \
    APP_CALLBACK_URL="" \
    WORKERS=1

EXPOSE 8000

# ============================================================
# ヘルスチェック
# ============================================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "\
import urllib.request, sys; \
try: \
    urllib.request.urlopen('http://localhost:8000/api/v1/streaming/health', timeout=5); \
    sys.exit(0) \
except: \
    sys.exit(1)"

# ============================================================
# 起動コマンド
# ============================================================
CMD ["./scripts/entrypoint.sh"]
