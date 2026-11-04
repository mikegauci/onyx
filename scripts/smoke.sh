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

skipped=0
for url in "$SITE" "$APP"; do
  headers="$(curl -sS -o /dev/null -D - ${bypass[@]+"${bypass[@]}"} "$url")"
  status="$(head -1 <<<"$headers" | awk '{print $2}')"
  if [ "$status" = "401" ] || [ "$status" = "403" ] \
    || { [ "$status" = "302" ] && grep -qi '^location: https://vercel.com/sso-api' <<<"$headers"; }; then
    echo "skip $url is behind deployment protection (HTTP $status); set VERCEL_BYPASS to check it"
    skipped=1
    continue
  fi
  for h in x-content-type-options x-frame-options referrer-policy; do
    grep -qi "^$h:" <<<"$headers" || fail "$url missing $h"
  done
  echo "ok   security headers on $url"
done
[ "$skipped" = 0 ] || { echo "smoke test passed with skipped checks"; exit 0; }
echo "smoke test passed"
