#!/usr/bin/env bash
# Smoke-test a deployed environment: scripts/smoke.sh <site-url> <platform-url> <api-url>
# Protected Vercel previews: export VERCEL_BYPASS=<automation bypass token> (never commit it).
set -euo pipefail

SITE="${1:?site url}"; APP="${2:?platform url}"; API="${3:?api url}"
APP_ORIGIN="$(sed -E 's#^(https?://[^/]+).*#\1#' <<<"$APP")"
fail() { echo "FAIL: $*" >&2; exit 1; }
bypass=()
[ -n "${VERCEL_BYPASS:-}" ] && bypass=(-H "x-vercel-protection-bypass: $VERCEL_BYPASS")

health="$(curl -fsS "$API/health")" || fail "API /health unreachable"
grep -q '"status":"ok"' <<<"$health" || fail "API unhealthy: $health"
echo "ok   api /health: $health"

allowed="$(curl -sS -o /dev/null -D - -X OPTIONS "$API/health" -H "Origin: $APP_ORIGIN" \
  -H "Access-Control-Request-Method: GET")"
grep -qi "^access-control-allow-origin: $APP_ORIGIN" <<<"$allowed" \
  || fail "CORS preflight not allowed for $APP_ORIGIN"
echo "ok   CORS allows $APP_ORIGIN"

refused="$(curl -sS -o /dev/null -D - -X OPTIONS "$API/health" -H "Origin: https://evil.example" \
  -H "Access-Control-Request-Method: GET")"
grep -qi "^access-control-allow-origin" <<<"$refused" && fail "CORS allowed an unknown origin"
echo "ok   CORS refuses https://evil.example"

for url in "$SITE" "$APP"; do
  headers="$(curl -sS -o /dev/null -D - "${bypass[@]}" "$url")"
  for h in x-content-type-options x-frame-options referrer-policy; do
    grep -qi "^$h:" <<<"$headers" || fail "$url missing $h"
  done
  echo "ok   security headers on $url"
done
echo "smoke test passed"
