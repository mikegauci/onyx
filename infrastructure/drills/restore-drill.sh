#!/usr/bin/env bash
# Backup and restore drill (PR-027). Dumps a database, restores it into a new empty one, and
# checks that the copy is complete and still isolated: same migration version, same row counts
# per table, row-level security on, and the app role still unable to bypass it.
#
#   infrastructure/drills/restore-drill.sh <source-url> <server-url-for-the-copy>
#
# Locally: the e2e database and the local server. For preview, the owner runs it with the
# preview connection string (never committed) and a throwaway local server for the copy.
set -euo pipefail

SOURCE="${1:?source database URL}"
SERVER="${2:?server URL for the restored copy, e.g. postgresql://user:pass@127.0.0.1:54322}"
COPY="onyx_restore_drill_$(date +%s)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

start=$(date +%s)
pg_dump --format=custom --no-owner --file "$WORK/backup.dump" "$SOURCE"
dumped=$(date +%s)
psql "$SERVER/postgres" -qc "CREATE DATABASE \"$COPY\""
# Roles are cluster-wide: the copy reuses the server's onyx_app / onyx_worker roles. Keep the
# grants (no --no-privileges): without them the app role can read nothing at all.
pg_restore --no-owner --dbname "$SERVER/$COPY" "$WORK/backup.dump"
restored=$(date +%s)

counts() {
  psql "$1" -Atc "SELECT string_agg(format('%s=%s', relname, n_live_tup), ',' ORDER BY relname)
                  FROM pg_stat_user_tables" >/dev/null
  psql "$1" -At <<'SQL'
SELECT table_name || '=' || (xpath('/row/n/text()',
       query_to_xml(format('SELECT count(*) AS n FROM %I', table_name), false, true, '')))[1]::text
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;
SQL
}
diff <(counts "$SOURCE") <(counts "$SERVER/$COPY") && echo "row counts: identical"

version=$(psql "$SERVER/$COPY" -Atc "SELECT version_num FROM alembic_version")
echo "migration version: $version"
no_rls=$(psql "$SERVER/$COPY" -Atc "SELECT count(*) FROM pg_class c JOIN pg_namespace n
  ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r'
  AND NOT c.relrowsecurity AND c.relname NOT IN ('alembic_version', 'modules')")
if [ "$no_rls" = "0" ]; then echo "row-level security: on for every tenant table"
else echo "FAILED: $no_rls tables without row-level security" >&2; exit 1; fi
leak=$(psql "$SERVER/$COPY" -qAtc "BEGIN; SET LOCAL ROLE onyx_app;
  SELECT count(*) FROM crm_contacts; ROLLBACK;")
if [ "$leak" = "0" ]; then echo "app role without a tenant: sees 0 contacts"
else echo "FAILED: the app role sees $leak contacts without a tenant" >&2; exit 1; fi

psql "$SERVER/postgres" -qc "DROP DATABASE \"$COPY\" WITH (FORCE)"
echo "dump $((dumped - start))s, restore $((restored - dumped))s, total $(( $(date +%s) - start ))s"
