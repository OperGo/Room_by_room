# Recovery readiness plan (Milestone 4, due 14 October 2026)

**Status: Route A selected; drill pending quote approval.** Prepared 6 October 2026. Nothing here has been
run against production.

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

**Selected (CTO, 6 October): route A.** It tests the recovery path that would really be used. It needs no founder time
and no external database access, which keeps the cloud coding environment and the founder's laptop out of
production data. Route C is not acceptable for "retained data".

## Tooling for route A (bounded PR, 6 October)

`python manage.py restore_fingerprint --database-url-env NAME`:
- reads the connection string from the named environment variable, so the URL never appears in a command or
  a log;
- routes **every query and file check** to that database for the run;
- runs it **read-only**: PostgreSQL refuses writes in that session;
- leaves the normal `DATABASE_URL` configuration untouched.

For local tests a SQLite copy is opened read-only (`mode=ro`) and must already exist; it is never created.

It refuses, without checking anything, in four cases:
- the variable is missing or empty;
- the URL is unsupported, incomplete or cannot be parsed (invalid port, malformed host). Parser
  messages are never shown;
- it names the source database itself;
- the database cannot be read. Only the error type is shown; never the URL, user, host or password.

## Drill steps (route A; CTO-corrected 6 October)

Nothing below is created or run until the CTO has obtained and recommended the exact temporary-instance quote and
the founder has approved the new spending. Cron command
changes are made only in an attended session, following the restore-always rules.

1. **Quiet window.** Pause application writes: the owner stops uploads and edits. Prove the complete queue is
   empty with `python manage.py receipt_jobs --limit 200`: the table is complete (fewer rows than the limit)
   and has no `queued` or `processing` rows.
2. **Source fingerprint.** Run one cron command `python manage.py restore_fingerprint`. Copy the log.
3. **Restore timestamp.** Record an explicit UTC timestamp **inside the write-free window** (after step 2,
   before writes resume).
4. **Wait** until that timestamp is eligible under Render's ten-minute recovery restriction.
5. **Restore to a separate temporary database** at that timestamp. **Never replace or restore over
   production.**
6. **Restored fingerprint.**
   - Set `RESTORE_DATABASE_URL` privately on the cron job, to the temporary instance's internal URL.
   - Run one cron command `python manage.py restore_fingerprint --database-url-env RESTORE_DATABASE_URL`.
7. **Restore the normal command** `python manage.py process_receipts --once` and **verify a successful
   run**. Do this always, including after a failure or interruption.
8. **Compare.**
   - The fingerprints must be identical.
   - Both must show zero `missing_references`, zero `size_mismatches` and zero
     `receipt_checksum_mismatches`.
   - Record the restore duration.
9. **Clean up** within the eventual approval: delete the temporary instance and remove `RESTORE_DATABASE_URL`.
   Then resume writes.

**Before creating anything:** the CTO obtains the **exact temporary-instance quote** from the dashboard and
recommends it; the founder approves the spending.

**Evidence to record:**
- both fingerprints (sanitised);
- the restore timestamp and duration;
- the quote and the actual cost;
- confirmation of cleanup.
