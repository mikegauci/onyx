#!/usr/bin/env bash
# Guard for destructive database commands: only local and test environments may run them.
set -euo pipefail
env="${ONYX_API_ENVIRONMENT:-local}"
case "$env" in
  local|test) ;;
  *) echo "Refusing: destructive database command in ONYX_API_ENVIRONMENT=$env" >&2; exit 1 ;;
esac
