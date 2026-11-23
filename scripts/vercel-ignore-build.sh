#!/usr/bin/env bash
# Vercel "Ignored Build Step". Exit 0 = skip the build, exit 1 = build.
# Preview builds always run. A production build runs only for a project whose Vercel
# environment has ONYX_ALLOW_PRODUCTION=1 (production target). The owner approved production
# for the platform (app.onyx.mt) and the site (onyx.mt) on 2026-11-23; any other project stays
# skipped until the owner approves it.
if [ "${VERCEL_ENV:-}" = "production" ] && [ "${ONYX_ALLOW_PRODUCTION:-}" != "1" ]; then
  echo "Skipping: production for this project is not approved (ONYX_ALLOW_PRODUCTION is not 1)."
  exit 0
fi
echo "Building ${VERCEL_ENV:-unknown} deployment."
exit 1
