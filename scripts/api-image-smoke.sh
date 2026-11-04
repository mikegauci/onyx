#!/usr/bin/env bash
# Start the API image with preview-like settings, wait for /health, then verify that
# misconfigured deployed settings make the container refuse to start.
set -euo pipefail

IMAGE="${1:?usage: api-image-smoke.sh <image>}"
NAME="onyx-api-smoke-$$"
PORT="${SMOKE_PORT:-18000}"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" -p "127.0.0.1:${PORT}:10000" \
  -e PORT=10000 \
  -e ONYX_API_ENVIRONMENT=preview \
  -e ONYX_API_CORS_ORIGINS=https://app-preview.example.test \
  "$IMAGE" >/dev/null

for _ in $(seq 1 30); do
  if body="$(curl -fsS "http://127.0.0.1:${PORT}/health" 2>/dev/null)"; then
    echo "health: $body"
    grep -q '"status":"ok"' <<<"$body"
    grep -q '"environment":"preview"' <<<"$body"
    break
  fi
  sleep 1
done
[ -n "${body:-}" ] || { docker logs "$NAME"; echo "API container never became healthy" >&2; exit 1; }

user="$(docker exec "$NAME" id -u)"
[ "$user" != "0" ] || { echo "container runs as root" >&2; exit 1; }
echo "runs as uid $user"

# A preview deployment with a localhost CORS origin must fail fast.
if docker run --rm -e ONYX_API_ENVIRONMENT=preview -e ONYX_API_CORS_ORIGINS=http://localhost:3001 \
  "$IMAGE" python -c "from app.main import app" >/dev/null 2>&1; then
  echo "expected invalid deployed settings to be rejected" >&2
  exit 1
fi
echo "invalid deployed settings rejected at startup"
