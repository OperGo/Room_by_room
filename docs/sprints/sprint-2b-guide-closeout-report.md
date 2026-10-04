ROOM BY ROOM — SPRINT 2B GUIDE CLOSEOUT REPORT TO CHATGPT CTO
Date: 4 October 2026
Status: ready for the founder. All three guide corrections are done and rehearsed from fresh shells with the published commands, in both networking cases. Application code is unchanged since the accepted preview build (cd5c3ea). Hosted behaviour remains unverified until the founder applies the checklist and deploys. No paid change, deployment or API spend.

1. OUTCOME
- External database access is corrected (docs/deployment-render-free-preview.md, "Database access rules").
  - Same region (Internal URL): the service needs no inbound rule. Only the founder's /32 is added, temporarily, and then removed.
  - Different regions (External URL plus PGSSLMODE=require on the service):
    - the service's outbound ranges come from Web service → Connect → Outbound and are kept permanently;
    - only the founder's /32 is added and removed;
    - if the ranges can't be established, stop that fallback and report it.
  - Never 0.0.0.0/0. Existing broad rules are replaced only after the needed rules are added.
  - /healthz/ (which checks the database) is checked after every rule removal.
- Temporary settings are scoped. A new helper, scripts/render_db.py, gives PGSSLMODE=require and DJANGO_ALLOW_INSECURE_KEY=1 only to the commands it starts. The guide contains no `export`, so nothing remains in the founder's shell.
  - The insecure-key override is local-only, and the guide forbids it on Render.
  - The local restore uses its own explicit settings (localhost, user, TLS preferred) and refuses non-local hosts.
- No password reaches process arguments. The External URL is read at a hidden prompt, and the password is written only to a temporary 0600 PGPASSFILE (in a 0700 directory). That file is deleted on success, error, Ctrl+C and SIGTERM.
  - pg_dump, createdb and pg_restore receive only non-secret host, port, user and database parameters.
  - The DATABASE_URL given to Django omits the password; libpq reads it from PGPASSFILE.
- Backups pause editing: the founder confirms, and the helper fingerprints before and after the export. If the data changed, it deletes the export. Exports are 0600, and restores go only into a new, isolated local database.
- Build command, start command, the ten environment settings, database storage, security flags, PYTHON_VERSION=3.13.14 and unset ANTHROPIC_API_KEY are unchanged, and a test guards them.

2. SCOPE
Delivered:
1. Access instructions per region case, with the health check after removal (guide sections "Before you start" and "Database access rules").
2. Scoped settings:
   - the helper keeps all temporary settings inside its child processes;
   - the guide forbids DJANGO_ALLOW_INSECURE_KEY on the service;
   - restore-check uses explicit local connection settings.
3. Credential-free arguments: the helper (create-owner, backup, restore-check) with PGPASSFILE, clean-up on every exit path, the editing pause with a fingerprint comparison, and private exports.
- Tests: tests/test_render_db_helper.py (6) and tests/test_free_preview_config.py (+1 guide guard: no exports, no "$DATABASE_URL", the helper commands, outbound ranges kept, the insecure key never on the service).
Deferred/incomplete, with reasons: the hosted deploy and walkthrough are the founder's next step. The real outbound ranges, IP rules and regions are unknown without Render access.
Departures from CTO brief, with reasons: none. The helper only wraps existing commands (create_owner, restore_fingerprint, pg_dump, createdb, pg_restore); no application feature was added.

3. CODE AND SETUP
Repository path, branch, commit(s), remote/PR only if actually created:
- /home/user/Room_by_room, branch sprint-2a.
- 0768ca7: helper, guide, tests and evidence; then this report commit.
- Pushed normally; the remote SHA is verified against HEAD in the handoff message.
- No PR, merge, deployment or Render change.
- Application files are identical to cd5c3ea (`git diff cd5c3ea HEAD -- apps config templates static requirements.txt manage.py` is empty).
FINAL FOUNDER CHECKLIST (tied to branch sprint-2a at the head SHA given in the handoff, which contains 0768ca7; the application code equals the rehearsed cd5c3ea):
1. Check the dashboard (no secrets):
   - the service and database regions, the PostgreSQL version (16/17/18 OK, otherwise stop) and the expiry date;
   - if the regions differ: Web service → Connect → Outbound ranges (if you can't find them, stop and report).
2. Existing free web service settings:
   - Repository OperGo/Room_by_room; branch sprint-2a; Auto-Deploy Off.
   - Build: pip install -r requirements.txt && python manage.py collectstatic --noinput
   - Start: python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 1 --timeout 120
   - Health check path: /healthz/
3. Environment, set on the service:
   - PYTHON_VERSION=3.13.14;
   - DJANGO_SECRET_KEY: generate it privately in Render;
   - DJANGO_DEBUG=0;
   - DATABASE_URL: the Internal URL (private);
   - PRIVATE_STORAGE_BACKEND=database; STATIC_MANIFEST=1;
   - DJANGO_HTTPS=1; DJANGO_SECURE_COOKIES=1;
   - RECEIPT_EXTRACTOR=anthropic; RECEIPT_MODEL=claude-haiku-4-5-20251001.
   Do not set ANTHROPIC_API_KEY or DJANGO_ALLOW_INSECURE_KEY.
   Different regions only: DATABASE_URL is the External URL, add PGSSLMODE=require, and add the service's outbound ranges as permanent database inbound rules.
4. Manual Deploy (branch head), then check /healthz/ → {"status": "ok"}.
5. Mac one-off setup:
   - Python 3.13;
   - PostgreSQL client tools of the database's major version (for backups);
   - git clone; git checkout sprint-2a; python3.13 -m venv .venv; source .venv/bin/activate; pip install -r requirements.txt
6. Add only your /32 to the database inbound rules, then run `python scripts/render_db.py create-owner alistair`. Paste the External URL at the hidden prompt, then type the password twice.
7. Remove your /32, leaving any service ranges in place. Check /healthz/ → {"status": "ok"}.
8. iPhone walkthrough (guide, last section).
9. Backups, weekly and before expiry: pause editing, add your /32, run `python scripts/render_db.py backup --out ~/RoomByRoomBackups`, remove your /32, check /healthz/, then run `python scripts/render_db.py restore-check <dump>` against a local PostgreSQL.
10. Send back only: the service URL, the service and database regions, the PostgreSQL version and the expiry date.

4. VALIDATION
Checks actually run and results:
- Focused tests: `pytest tests/test_render_db_helper.py tests/test_free_preview_config.py` → 11 passed.
  - The helper tests cover:
    - the passfile is 0600 in a 0700 directory, with escaped contents;
    - the password is absent from arguments and from the child environment;
    - the DATABASE_URL given to children has no password, and PGSSLMODE=require;
    - the passfile is removed on an exception;
    - the caller's environment is unchanged;
    - leftover PG*, DATABASE_URL and override settings are scrubbed;
    - a URL without a password is refused;
    - restore-check refuses a remote host.
  - Sanity check: `pytest` (SQLite) → 233 passed, 8 skipped. Per the CTO, the unchanged application suites and screenshots were not repeated on PostgreSQL or in the browser.
- Rehearsal of the published commands (docs/sprints/evidence/sprint-2b-guide-closeout-rehearsal.txt).
  - Setup:
    - the exact start command from a fresh build;
    - PG 18.6 with TLS-only TCP rules standing in for the inbound IP rules;
    - relays standing in for the founder's IP (127.0.0.2) and the service's outbound range (127.0.0.3);
    - a local PG 18.6 without TLS for the restore;
    - each founder command run in a fresh `env -i … bash --noprofile --norc` shell.
  - Case A, same region (Internal URL):
    - With no rules, the service was healthy and the founder was refused. After adding the founder's /32 the founder could connect.
    - `create-owner alistair` succeeded, and so did the 21/21 phone walkthrough against the service.
    - `backup` wrote 99,426 bytes with 3 files and 1 confirmed purchase; both files are -rw-------.
    - After removing the /32, the founder was refused and the service stayed healthy (200).
    - `restore-check` into the laptop PG without TLS printed IDENTICAL.
  - Case B, different regions (External URL plus PGSSLMODE=require):
    - With only the service range, the service was healthy. After adding the founder's /32 alongside it, `backup` succeeded.
    - After removing only the /32, the founder was refused, the service stayed healthy (200) and `restore-check` printed IDENTICAL.
    - Negative control: replacing all rules with the founder's IP made the service fail to start (health 000). Restoring the service rule brought back 200. This is the failure the guide now prevents.
  - Leaks:
    - After every helper run, the founder shell held no PG*, DATABASE_URL or DJANGO_ALLOW* settings, and no /tmp/rbr-* passfile remained.
    - A /proc monitor sampled about 3,170 times across 42 founder-session processes. No argument list or environment contained the database password or the owner password.
  - Failure clean-up (passfile gone, shell clean, every time):
    - wrong password (exit 1, with an actionable hint);
    - SIGTERM at create_owner's password prompt (exit 143);
    - Ctrl+C ("Cancelled", exit 130);
    - pg_dump 16 against a PG 18 server ("server version mismatch"; the partial export was removed, leaving no file).
  - Contrast with the old guide pattern: `export PGSSLMODE=require …` then a local TCP createdb/dropdb failed with "server does not support SSL, but SSL was required". The same local operation with the helper's explicit local settings succeeded.
Screens inspected and viewport widths: not applicable (no UI change). The walkthrough within the rehearsal passed 21/21.
Actual screenshots: none new (the existing docs/screenshots/sprint2b-preview/ is unchanged).
Failed tests, untested behaviour and limitations:
- Rehearsal-harness issues fixed during the sprint (test code only):
  - a prompt driver that blocked on read;
  - a leak monitor first scoped to all processes, which flagged the harness and the simulated Render service (both legitimately hold DATABASE_URL); it is now limited to founder-session processes;
  - the first contrast check used a Unix socket, where libpq ignores PGSSLMODE; it now uses TCP localhost.
- Not verified:
  - Render's dashboard labels and behaviour (Access Control, Connect → Outbound);
  - real outbound ranges and region latency;
  - macOS specifics (the rehearsal ran on Linux with the same Python and PostgreSQL clients);
  - the hosted deploy and the iPhone.
- SIGKILL of the helper cannot run clean-up. The passfile would then stay in the OS temporary folder (0600, in a 0700 directory) until the system clears it. This is noted here and not hidden.

5. COST INTEGRITY
Unchanged application code. The rehearsal's walkthrough again confirmed: refusal until reconciliation, a single posting, an idempotent repeat confirmation, and totals counted once. The backup and restore fingerprints matched on totals (£12.50, 1 confirmed purchase).

6. RECEIPT PROCESSING
Unchanged. The preview has no key or worker, and manual entry only ("Automatic extraction not configured"). No live calls; usage not measured.

7. RISKS / DECISIONS FOR CTO
- Different-region fallback depends on Render showing the service's outbound ranges. If it doesn't, the guide stops that path and asks for a report (no 0.0.0.0/0).
- The free database's expiry (30 days, then 14 days of grace, then deletion) remains the main data risk. Weekly helper backups and restore checks are the mitigation.
- Later paid release (CTO decision recorded): upgrade the existing service and database in place, add the worker, preserve the database's major version, inventory the resources and confirm the quote first. Do not apply the current Blueprint alongside them. Not yet approved.
Access gaps: no Render access (regions, version, expiry, outbound ranges and rules come from the founder), and no iPhone, real receipts or API key.

8. FOUNDER REVIEW
Follow the FINAL FOUNDER CHECKLIST in section 3, then the guide's iPhone walkthrough (about 10 minutes). Send back only: the service URL, the service and database regions, the PostgreSQL version and the expiry date, plus anything slow or wrong on the phone. Never send URLs containing passwords.
