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

Write these down; the report asks for them back. **None of them are secrets.**

| Where | Field |
|---|---|
| Web service → top of the page / Settings | Service name; service ID (`srv-…`); instance type (should say *Free*); **region** |
| Web service → Settings | Repository; branch; Build command; Start command; Auto-Deploy |
| Database → Info | Database name; ID (`dpg-…`); **region**; **PostgreSQL version**; created date and the **expiry date** shown for free databases; storage (1 GB) |
| Database → Networking / Access Control | The current inbound IP rules (who may connect from outside Render) |

**Two checks before deploying:**

1. **Same region.** The service and the database must be in the same region for the database's
   *Internal* URL to work.
   - If they differ, do **not** replace either. Use the database's **External** URL as `DATABASE_URL` and
     add `PGSSLMODE=require` to the service. This works because the connection then goes over TLS (rehearsed
     locally). Expect slightly slower pages, and report it.
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
| `DATABASE_URL` | **Private.** The existing database's **Internal Database URL** (Database → Connect → Internal). Use the External URL only in the different-region case above. |
| `PRIVATE_STORAGE_BACKEND` | `database` |
| `STATIC_MANIFEST` | `1` |
| `DJANGO_HTTPS` | `1` |
| `DJANGO_SECURE_COOKIES` | `1` |
| `RECEIPT_EXTRACTOR` | `anthropic` |
| `RECEIPT_MODEL` | `claude-haiku-4-5-20251001` |

- **Leave `ANTHROPIC_API_KEY` unset.** Automatic reading then shows "Automatic extraction not configured.
  Enter the details from the receipt." Manual review and confirmation work normally.
- There is no receipt worker in this preview. Do not add one: no worker inside Gunicorn, no background
  threads, no fake extractor.
- Render sets `RENDER_EXTERNAL_HOSTNAME` itself, so the `onrender.com` address is allowed automatically.
- Add `PGSSLMODE=require` **only** in the different-region case.

### D. Deploy
1. Save the settings, then **Manual Deploy**.
2. In the build log, expect `Successfully installed … gunicorn-26.2.0 … whitenoise-6.12.0` and
   `… static files copied …, … post-processed`.
3. In the runtime log, expect `Applying …` lines (first deploy only), then `Booting worker`.
4. Open `https://<service>.onrender.com/healthz/`. Expect `{"status": "ok"}`.
5. Open the root address. Expect the sign-in page; there is no signup.

## Creating the owner account (no Render Shell on free services)

Run the interactive `create_owner` command **once** from your own trusted computer, connected to the
database's **External** URL over TLS. The password is typed only at the hidden prompts: never in a command,
file, chat or report.

1. **One-off setup (macOS):**
   - Install Python 3.13 (python.org installer or `brew install python@3.13`).
   - Clone the repository and install dependencies:
     ```bash
     git clone https://github.com/OperGo/Room_by_room.git && cd Room_by_room
     git checkout sprint-2a          # the same commit you deployed
     python3.13 -m venv .venv && source .venv/bin/activate
     pip install -r requirements.txt
     ```
2. **Allow your computer only.** Open Database → Networking → Access Control (inbound IP rules).
   - If anything broader than your own address is allowed (for example `0.0.0.0/0`), replace it with **only
     your current public IP** (the dashboard offers "Add my IP", or use the address shown by
     `curl -s https://checkip.amazonaws.com`), as `x.x.x.x/32`.
   - If external access is already blocked, add only that `/32` rule.
3. **Create the account** in the same terminal:
   ```bash
   read -rs DATABASE_URL     # paste the External Database URL, press Enter (hidden, not saved in history)
   export DATABASE_URL PGSSLMODE=require DJANGO_DEBUG=0 DJANGO_ALLOW_INSECURE_KEY=1
   python manage.py create_owner alistair
   # Password: ••••••   Password (again): ••••••
   unset DATABASE_URL
   ```
   - `PGSSLMODE=require` forces TLS. The app's `DATABASE_URL` parser ignores `?sslmode=` in the URL, but the
     PostgreSQL driver honours this variable. It was rehearsed: a server without TLS is refused.
   - `DJANGO_ALLOW_INSECURE_KEY=1` only lets the command start without the service's secret key. Password
     hashing does not use the secret key, so the service's key never needs to leave Render.
   - The command refuses an existing username, mismatched entries and weak passwords (Django's validators).
     It creates an empty account.
4. **Close external access** by removing your `/32` rule, so nothing outside Render can connect. Reopen it
   the same way only for backups.
5. Sign in on the iPhone at the `onrender.com` address.

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

Use your own computer. Open your `/32` rule as in "Creating the owner account" step 2, and close it again
afterwards.

**Version rule:** your `pg_dump` must be the **same major version as the database or newer**. Rehearsed:
pg_dump 16 refused a PostgreSQL 18 server with "server version mismatch". Install the matching client, for
example `brew install postgresql@18`, or Postgres.app.

1. **Fingerprint the live data.** It holds counts, hashes and totals only, no content:
   ```bash
   read -rs DATABASE_URL; export DATABASE_URL PGSSLMODE=require DJANGO_DEBUG=0 DJANGO_ALLOW_INSECURE_KEY=1 PRIVATE_STORAGE_BACKEND=database
   python manage.py restore_fingerprint > before.json
   ```
2. **Dump.** Keep the file only on encrypted storage; it contains your receipts and photos:
   ```bash
   pg_dump -Fc --no-owner --no-acl -f "room-by-room-$(date +%F).dump" "$DATABASE_URL"
   unset DATABASE_URL
   ```
3. **Restore test** into an isolated local PostgreSQL of the same major version. No Render resources are
   needed:
   ```bash
   createdb rbr_restore
   pg_restore --no-owner --no-acl --exit-on-error -d rbr_restore room-by-room-YYYY-MM-DD.dump
   DATABASE_URL=postgres://localhost/rbr_restore PRIVATE_STORAGE_BACKEND=database DJANGO_DEBUG=1 \
     python manage.py restore_fingerprint > after.json
   diff before.json after.json && echo IDENTICAL
   ```
   Then delete the local copy (`dropdb rbr_restore`) if it is no longer needed.

Do this **weekly**, and **always before the expiry date** or any plan change. Rehearsed locally on
PostgreSQL 18.6: fingerprints were identical (3 files, total £12.50, 1 confirmed purchase). Evidence:
`docs/sprints/evidence/sprint-2b-backup-restore.txt`.

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
8. Sign out, then try a bookmarked receipt link. Expect the sign-in page, not the file.
9. Report back:
   - anything slow (note wake-ups separately);
   - anything that looks wrong on the phone;
   - the dashboard fields from "Before you start".
