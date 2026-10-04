# Free preview on Render: founder-applied checklist

**Status:** prepared and rehearsed locally. **Not yet applied.** The founder applies these settings to the
resources he already created and runs the manual deploy. Hosted behaviour is **unverified** until then.

This preview uses the founder's existing **free** web service and **free** PostgreSQL database in the
"Room by Room" project. Do not apply the paid Blueprint (`render.yaml`) and do not create replacement
resources. The paid plan is kept separately in `docs/deployment-render.md`.

## Why the first deploy failed (from the supplied log)

| Symptom in the log | Cause | Fix in this checklist |
|---|---|---|
| Stops at `DJANGO_SECRET_KEY must be set` | Variable not set on the service | Set it privately (step C) |
| `pip install` / `collectstatic` run as the **start** command | Build and start commands swapped or merged | Separate build and start commands (step B) |
| Python 3.14.3 | Render's default Python version, used because `PYTHON_VERSION` was not set | `PYTHON_VERSION=3.13.14` |
| Dependencies older than Sprint 2A | The service was probably built from `sprint-1` or `sprint-2`; neither contains Gunicorn, WhiteNoise or DatabaseStorage | Branch `sprint-2a` (step A) |

Only `sprint-2a` contains the deployable code, checked on the remote branches on 4 October 2026:
`gunicorn==26.2.0`, `whitenoise==6.12.0`, and `DatabaseStorage` in `apps/core/storage.py`.

## Before you start: read these from the dashboard (I have no Render access)

Check these yourself. Afterwards, send back only: **service URL, service and database regions, PostgreSQL
version and expiry date.** None of these are secrets. Never send URLs containing passwords.

| Where | Field |
|---|---|
| Web service → top of the page / Settings | Service name; service ID (`srv-…`); instance type (should say *Free*); **region** |
| Web service → Settings | Repository; branch; Build command; Start command; Auto-Deploy |
| Database → Info | Database name; ID (`dpg-…`); **region**; **PostgreSQL version**; created date and the **expiry date** shown for free databases; storage (1 GB) |
| Database → Networking / Access Control | The current inbound IP rules (who may connect from outside Render) |
| Web service → Connect → Outbound | Only if the regions differ: the service's outbound IP ranges |

**Two checks before deploying:**

1. **Same region?** Compare the service's and the database's regions.
   - **Same region (expected):** the service uses the database's **Internal** URL. It connects over Render's
     private network, so the database's inbound IP rules do not affect it.
   - **Different regions:** do **not** replace either resource. The service must use the **External** URL
     with `PGSSLMODE=require`, and the database must allow the service's outbound addresses (see "Database
     access rules" below). If you cannot find those outbound ranges, stop and report it. Never open
     `0.0.0.0/0`.
2. **PostgreSQL version.** The application and its full test suite were checked on PostgreSQL **16.14,
   17.11 and 18.6**. A new free database most likely runs 18 (Render's current default).
   - 16, 17 or 18: go ahead.
   - Anything else: stop and report it. Do not replace or downgrade the database.

## Founder checklist: existing free web service

### A. Source
- **Repository:** `OperGo/Room_by_room`
- **Branch:** `sprint-2a`. Deploy the final preview-preparation commit named in the Sprint 2B report
  (Manual Deploy → "Deploy a specific commit", or "latest commit" if the branch head is that commit).
- **Auto-Deploy:** **Off**

### B. Commands
- **Build command:**
  ```
  pip install -r requirements.txt && python manage.py collectstatic --noinput
  ```
- **Start command:**
  ```
  python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 1 --timeout 120
  ```
  Free web services have no pre-deploy command, so this single-instance preview runs migrations just before
  Gunicorn starts. With one instance there is no race. On a wake-up with nothing to migrate it is a quick no-op.
- **Health check path:** `/healthz/` (Settings → Health Checks, if the field is offered for the instance).

### C. Environment (service → Environment)

A manually created service does **not** inherit the Blueprint's `room-by-room-shared` group. Add each
variable directly on the service.

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.13.14` |
| `DJANGO_SECRET_KEY` | **Private.** Use Render's "Generate" button for the value, or paste the output of `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` run on your own machine. Never copy it anywhere else. |
| `DJANGO_DEBUG` | `0` |
| `DATABASE_URL` | **Private.** The existing database's **Internal Database URL** (Database → Connect → Internal). Only in the different-region case: the External URL (with the access rules below). |
| `PRIVATE_STORAGE_BACKEND` | `database` |
| `STATIC_MANIFEST` | `1` |
| `DJANGO_HTTPS` | `1` |
| `DJANGO_SECURE_COOKIES` | `1` |
| `RECEIPT_EXTRACTOR` | `anthropic` |
| `RECEIPT_MODEL` | `claude-haiku-4-5-20251001` |

- **Leave `ANTHROPIC_API_KEY` unset** until the receipt-reading pilot is approved (`docs/receipt-pilot.md`
  says how and where to add it privately). Automatic reading then shows "Automatic extraction not configured.
  Enter the details from the receipt." Manual review and confirmation work normally.
- There is no receipt worker in this preview. Do not add one: no worker inside Gunicorn, no background
  threads, no fake extractor.
- Render sets `RENDER_EXTERNAL_HOSTNAME` itself, so the `onrender.com` address is allowed automatically.
- Add `PGSSLMODE=require` to the service **only** in the different-region case (External URL).
- Never add `DJANGO_ALLOW_INSECURE_KEY` to the service. It is only for the local helper commands below.

### D. Deploy
1. Save the settings, then **Manual Deploy**.
2. In the build log, expect `Successfully installed … gunicorn-26.2.0 … whitenoise-6.12.0` and
   `… static files copied …, … post-processed`.
3. In the runtime log, expect `Applying …` lines (first deploy only), then `Booting worker`.
4. Open `https://<service>.onrender.com/healthz/`. Expect `{"status": "ok"}`.
5. Open the root address. Expect the sign-in page; there is no signup.

## Database access rules (inbound IP rules)

External connections to the database are controlled under **Database → Networking → Access Control**
(inbound IP rules). The rules you need depend on the region case.

**Same region (service uses the Internal URL).**
- The service needs **no** inbound rule.
- Keep external access closed. Add only **your own `/32` temporarily**, while creating the account or
  taking a backup. Then remove that rule.

**Different regions (service uses the External URL).**
- Find the service's outbound addresses at **Web service → Connect → Outbound**.
- Add each listed range as an inbound rule on the database. **Keep these rules permanently**: without them
  the app cannot reach its database.
- If the Outbound tab is missing, or you cannot tell which ranges to use, **stop this fallback and report
  it**. Do not guess, and do not open `0.0.0.0/0`.
- Add and remove **only your own `/32`** around account setup and backups. Never replace or clear the
  service's ranges.

In both cases:
- Never use `0.0.0.0/0`.
- If the rules currently contain `0.0.0.0/0`, **first** add the rules this case needs (your `/32`, plus the
  service's outbound ranges if regions differ). Then remove `0.0.0.0/0`, and record that you changed it.
- After removing your `/32`, open `https://<service>.onrender.com/healthz/` and expect `{"status": "ok"}`.
  That page checks the database, so it proves the service still has access.

Your current public IP is shown by the dashboard's "Add my IP" option or by `curl -s https://checkip.amazonaws.com`.
Write it as `x.x.x.x/32`.

## Your computer: one-off setup (macOS)

- Install Python 3.13 (python.org installer or `brew install python@3.13`).
- For backups, also install the PostgreSQL client tools of the **same major version as the database or
  newer**, for example `brew install postgresql@18` or Postgres.app.
- Then clone the repository and install its dependencies:

```bash
git clone https://github.com/OperGo/Room_by_room.git && cd Room_by_room
git checkout sprint-2a                     # the commit you deployed
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

All database work goes through `scripts/render_db.py`. It does the following:
- asks for the **External Database URL at a hidden prompt**, so the URL is never typed into a command or
  saved in shell history;
- puts the password only in a temporary private file (permission 0600, `PGPASSFILE`). The file is deleted
  on success, on error, on Ctrl+C and on termination, and the password never appears in any process's
  arguments;
- gives its temporary settings only to the commands it starts, so **nothing is left behind in your
  shell**. These settings are `PGSSLMODE=require` (TLS for every remote connection) and
  `DJANGO_ALLOW_INSECURE_KEY=1` (lets local management commands run without the service's secret key);
- **never** asks you to `export` anything.

## Creating the owner account (no Render Shell on free services)

1. Add **only your `/32`** to the database's inbound IP rules ("Database access rules" above).
2. Run this in the `Room_by_room` folder, with the virtualenv active:
   ```bash
   python scripts/render_db.py create-owner alistair
   ```
   1. Paste the **External Database URL** when asked. Nothing is shown.
   2. Type the new password twice at the hidden `Password:` prompts.
   - It refuses an existing username, mismatched entries and weak passwords (10+ characters, Django's
     validators), and it creates an empty account.
   - Password hashing does not use the service's secret key, so that key stays in Render.
3. **Remove your `/32` rule.** In the different-region case, leave the service's rules in place.
4. Check `https://<service>.onrender.com/healthz/` → `{"status": "ok"}`, then sign in on the iPhone.

## Forgotten password

The app has no "forgot password" link (there is no email or signup). Reset it from your computer:

1. Add **only your `/32`** to the database's inbound IP rules.
2. Run `python scripts/render_db.py change-password alistair`.
   1. Paste the External Database URL (hidden).
   2. Type the new password twice (hidden; same rules as account creation).
3. Remove your `/32`, then check `/healthz/` → `{"status": "ok"}`.

## Preview limits (free plan)

- **Spin-down:** the service sleeps after 15 minutes without traffic.
  - The first visit after that takes about a minute while it wakes, and migrations run again (a no-op).
  - Render may also restart free services at any time.
  - Free instance hours are limited per workspace each month.
- **30-day database:** the free database **expires 30 days after creation**. After a 14-day grace period
  (upgrade only) Render **deletes it with all data**, including receipts and photos.
  - Note the expiry date from the dashboard.
  - Treat preview data as disposable unless exported (see below).
  - Upgrading is a cost decision for the CTO and founder.
- **No managed backups** on free Postgres: there is no point-in-time recovery and no Render exports.
- **Capacity:** the free database has 1 GB. Receipts and photos are stored inside it
  (`PRIVATE_STORAGE_BACKEND=database`): roughly 300–500 receipts.
- **No automatic reading** (no worker, no key). Manual entry and confirmation are fully available.

## Manual backup and restore (free database)

Free Postgres has no managed backups. Take one **weekly** and **always before the expiry date** or any plan
change.

1. **Pause editing.** Close the app on your phone and in any browser until the backup finishes. The helper
   fingerprints the data before and after the export. If anything changed in between, it deletes the export
   and asks you to run it again.
2. Add **only your `/32`** to the database's inbound IP rules.
3. Run:
   ```bash
   python scripts/render_db.py backup --out ~/RoomByRoomBackups
   ```
   1. Confirm with `y`.
   2. Paste the External Database URL when asked (hidden).

   It writes `room-by-room-YYYY-MM-DD.dump` and `room-by-room-YYYY-MM-DD.fingerprint.json`, both readable
   only by you. Keep them **private, on encrypted storage**: the dump contains your receipts and photos. If
   your `pg_dump` is older than the server, it stops with "server version mismatch" and leaves no partial
   file. Install the matching client tools and retry (or point `--pg-bin` at them).
4. **Remove your `/32` rule.** Check `/healthz/` → `{"status": "ok"}`.
5. **Restore test** into an **isolated local** PostgreSQL of the same major version. No Render resources
   and no network are involved:
   ```bash
   python scripts/render_db.py restore-check ~/RoomByRoomBackups/room-by-room-YYYY-MM-DD.dump
   ```
   - It uses explicit local settings (`localhost:5432`, your user name, TLS *preferred*), independent of
     anything used for the remote database. Change them with `--host`, `--port`, `--user` or `--db` if
     needed.
   - It refuses non-local hosts and refuses to restore over an existing database.
   - It prints `IDENTICAL` when the restored copy matches the backup's fingerprint: same file contents,
     totals and row counts.
   - Delete the copy afterwards with `dropdb rbr_restore`.

## What was rehearsed locally (and what was not)

Rehearsed locally, using fictional data and no paid calls, on:
- PostgreSQL 18.6 with TLS-only external access;
- a fresh Python 3.13.14 virtualenv built with the exact build command;
- the exact start command, run with production settings and one Gunicorn worker.

The results (evidence: `docs/sprints/evidence/sprint-2b-free-preview-rehearsal.txt`):
- `/healthz/` returned 200, and plain HTTP redirected to HTTPS with HSTS.
- Static files were hashed and cached for a long time. The session cookie was Secure and HttpOnly.
- `create_owner` worked interactively over TLS.
- Private photo and receipt files were served to the owner. Anonymous users were redirected; another
  account got 404.
- The missing-key message showed.
- Manual confirmation was refused until the items reconciled, then posted exactly once. Repeat confirmation
  returned the same purchase.
- 17 pages showed no sideways scrolling at 390 px and an iPhone-like pixel density.
- The full test suite passes on PostgreSQL 16, 17 and 18.

The helper and access rules were rehearsed from fresh shells with the published commands (evidence:
`docs/sprints/evidence/sprint-2b-guide-closeout-rehearsal.txt`). Local stand-ins played the founder's IP,
the service's outbound range and a laptop PostgreSQL without TLS. Both region cases passed:
- Adding and removing the founder's temporary `/32` left the service healthy.
- Replacing all rules with the founder's IP broke the external-URL service, which is why the guide forbids
  it.
- Owner creation, backup and restore checks were identical across runs.
- No settings were left in the shell, and no temporary passfile was left after a wrong password, SIGTERM,
  Ctrl+C or a too-old `pg_dump`.
- No founder-side process ever had the password in its arguments or environment.

A local TLS proxy stood in for Render's HTTPS edge. **Not verified:** Render's own build, proxy, health
check, spin-down and the founder's actual database. These depend on the founder applying this checklist.

## Founder walkthrough after the deploy (about 10 minutes, iPhone)

1. Open `https://<service>.onrender.com/healthz/`. Expect `{"status": "ok"}`. Allow up to a minute if the
   service was asleep.
2. Open the root address. Expect the sign-in page. Sign in as `alistair`. Expect an empty home page.
3. Projects → New: create a project with a budget. Then add a photo from the camera roll.
4. Costs → Add receipt: take a photo of a receipt.
   - Expect "Automatic extraction not configured. Enter the details from the receipt."
5. Enter the merchant, date, total and items, and choose the project.
   - Try a total that doesn't match first. Expect "Nothing was recorded…" with your entries kept.
   - Correct it, check that "Matches total" shows, and press Confirm purchase once.
6. Costs: the total equals the receipt, counted once. The project shows the same net cost.
7. Tap "Open original" on the receipt and open the project photo. Both should display.
8. Copy a receipt's "Open original" link. Then, on the phone, go to Home, scroll to the bottom and tap
   **Sign out** ("Signed in as …"). Open the copied link in the same browser: expect the sign-in page, not
   the file. (On a laptop, Sign out is at the foot of the side menu.)
9. Report back (no secrets):
   - the service URL;
   - the service and database regions;
   - the PostgreSQL version and the expiry date;
   - anything slow (note wake-ups separately);
   - anything that looks wrong on the phone.
