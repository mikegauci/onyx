#!/usr/bin/env bash
# Vercel "Ignored Build Step". Exit 0 = skip the build, exit 1 = build.
# PR-002: production deployments are not approved yet, so every production build is skipped.
# Preview builds always run. Remove the production guard only with explicit owner approval.
if [ "${VERCEL_ENV:-}" = "production" ]; then
  echo "Skipping: production deployments require explicit owner approval (PR-002)."
  exit 0
fi
echo "Building ${VERCEL_ENV:-unknown} deployment."
exit 1
