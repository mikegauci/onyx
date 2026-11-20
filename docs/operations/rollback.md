# Deploy rollback (PR-027)

| Part                        | How                                                                                           |
| --------------------------- | --------------------------------------------------------------------------------------------- |
| Dashboard and site (Vercel) | Project → Deployments → the last good one → **Promote** (instant)                             |
| API (Render)                | Service → Events → the last good deploy → **Rollback**                                        |
| Worker (Render, later)      | Same as the API; workflows continue from Temporal's history                                   |
| Database                    | Never down-migrate a deployed database. Fix forward with a new migration, or restore a backup |

Order: roll back the API before the dashboard when a release changed both (the dashboard
expects the API's contract). A rolled-back API must still work with the newest migration,
which is why migrations only add columns and tables, never rename or drop them in the same
release.

Workflow code: a rollback must still replay running workflows' histories. The replay test
(`tests/workflows/test_replay.py`) guards this for each release.

After a rollback: say so in the PR, open a fix PR, and redeploy through CI.
