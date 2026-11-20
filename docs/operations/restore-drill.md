# Backup and restore drill (PR-027)

`infrastructure/drills/restore-drill.sh <source-url> <server-url>` dumps a database, restores
it into a new empty database and checks the copy:

- the same row count in every table;
- the same migration version;
- row-level security on for every tenant table;
- the app role, without a tenant, sees nothing.

It drops the copy at the end and prints the timings.

## Results

| Date        | Source                         | Result | Dump | Restore |
| ----------- | ------------------------------ | ------ | ---- | ------- |
| 20 Nov 2026 | Local e2e database (seed data) | Passed | 0 s  | 1 s     |

The first run found a real problem: restoring with `--no-privileges` dropped every grant, so
the app role could read nothing. Restores must keep privileges (the script does).

## Preview and production (owner)

The connection strings are the owner's. For `onyx-preview`:

1. Supabase → `onyx-preview` → Connect → Session pooler: copy the `postgres` connection
   string.
2. Run the drill with that as the source and a local Postgres 17 as the server (`make up`):

   ```bash
   infrastructure/drills/restore-drill.sh "<preview url>" "postgresql://onyx:onyx_local_only@127.0.0.1:54322"
   ```

   The local server needs the `onyx_app` and `onyx_worker` roles, which `make db-migrate`
   creates.

3. Add the result to the table above.

Supabase's own backups: the free plan keeps no point-in-time recovery. Before live client
data, production needs a plan with daily backups (and ideally point-in-time recovery), and
this drill against a restored backup. That is a billable change for the owner.
