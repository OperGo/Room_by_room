# Recovery readiness plan (Milestone 4, due 14 October 2026)

Prepared 6 October 2026. **A CTO decision on the route is needed.** Nothing here has been run against
production.

## What "recovered" must mean

Real receipts and photos live **inside PostgreSQL** (`PRIVATE_STORAGE_BACKEND=database`, `core.StoredFile`),
so restoring the database restores the files too. A restore passes only if the restored copy's
`restore_fingerprint` output is **identical** to the source's, taken at the same moment with no writes in
between. That output covers:
- per-file SHA-256 digests for receipts and photos;
- the overall and per-project money totals;
- row counts for every model.

The command is read-only and prints no names, merchants or file bytes, so its output can go into the evidence.

## Routes

| Route | How | Proves | Cost / access | Founder effort |
|---|---|---|---|---|
| **A. Render managed recovery** (recommended, if the plan offers it) | The CTO confirms what the paid `0.1c-256mb` plan offers (daily backups, point-in-time recovery to a **new** instance). Take a source fingerprint, restore to a temporary new instance, take the restored fingerprint, compare, delete the temporary instance. | The backups that would actually be used in an incident can be restored, files included | The temporary instance is **new spending** (prorated, likely cents; founder approval via the CTO). Getting a fingerprint from inside Render needs a small change (below). | None |
| B. Logical dump to the founder's laptop | `scripts/render_db.py backup` (pg_dump through a temporary `/32` access rule), then `restore-check` into a local PostgreSQL | A portable off-Render copy can be restored | No Render spend. It needs a temporary external-access rule, a local PostgreSQL on the Mac (Homebrew had to compile it on macOS 14) and about 30–45 minutes of founder time. | High |
| C. Rely on managed backups untested | — | Nothing | — | — |

**Recommendation: route A.** It tests the recovery path that would really be used. It needs no founder time
and no external database access, which keeps the cloud coding environment and the founder's laptop out of
production data. Route C is not acceptable for "retained data".

## Change route A needs (small, bounded PR if chosen)

On Render, the only way to run a command is the cron job's command, and the restored instance has its own
internal URL. Two parts:
- **Command option:** `restore_fingerprint --database-url-env NAME` reads the connection string from the named
  environment variable. The URL then never appears in the command text or the logs.
- **Temporary private variable:** the CTO sets `RESTORE_DATABASE_URL` on the cron job. The cron command is
  swapped to `python manage.py restore_fingerprint --database-url-env RESTORE_DATABASE_URL` for one run, then
  restored. The swap follows the same restore-always rules as the failure check.

The source fingerprint uses the normal `DATABASE_URL`, taken at a moment with no uploads.

## Drill steps (route A)

1. Agree a quiet time and pause uploads. Wait for an empty queue (proven by the complete `receipt_jobs`
   table).
2. Take the source fingerprint: one cron run of `python manage.py restore_fingerprint`. Copy the log.
3. Start the restore to a new temporary instance. Use the point in time just after step 2, or the latest
   backup if point-in-time recovery is not offered.
4. Take the restored fingerprint (the command above), then **restore the normal cron command** and check that
   a normal run happens.
5. Compare the two outputs; they must be identical. Record the restore duration and the instance cost.
6. Delete the temporary instance and the `RESTORE_DATABASE_URL` variable, then resume uploads.

**Evidence to record:**
- both fingerprints (sanitised);
- timings;
- the restored point in time;
- the cost;
- the confirmation that the temporary instance and variable were deleted.

## Decisions needed (CTO)

1. Route A or B.
2. For route A:
   - confirm the plan's backup and point-in-time recovery options on the dashboard;
   - put the temporary instance's cost to the founder as new spending;
   - authorise the small `--database-url-env` PR.
