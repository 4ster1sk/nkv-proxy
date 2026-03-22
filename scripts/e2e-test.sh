#!/usr/bin/env bash
# Run e2e tests for nkv-proxy against real Nekonoverse instance.
# Everything runs inside Docker - no local Python needed.
# Usage: ./scripts/e2e-test.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Building and starting e2e services ==="
docker compose -f docker-compose.e2e.yml up -d --build --wait

echo "=== Running e2e tests ==="
docker compose -f docker-compose.e2e.yml run --rm test-runner
EXIT_CODE=$?

echo "=== Stopping e2e services ==="
docker compose -f docker-compose.e2e.yml down -v

exit $EXIT_CODE
