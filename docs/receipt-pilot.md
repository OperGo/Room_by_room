# Live receipt-reading pilot: founder checklist (Sprint 2C)

**Status:** prepared, **not approved or applied**. Nothing in this guide may be bought, created or deployed
until the founder explicitly approves the pilot budget and has checked the Render dashboard quote.

**Goal:** prove live receipt reading through to accurate, confirmed costs on the existing preview
(https://room-by-room.onrender.com/).

**Proposed budget:**
- one Render background worker, Starter (0.5c-512mb), about **US$7/month**, for at most one month;
- **US$5 in total** of Anthropic API usage, capped by a spend limit.

## Which procedure is this?

| Procedure | Use it for | Document |
|---|---|---|
| **Pilot (this guide)** | Adds **one worker** next to the **existing** free web service and the existing PostgreSQL 18 database. | `docs/receipt-pilot.md` |
| Future in-place upgrade | Moves the existing web service and database to paid plans (and keeps the worker), only after separate approval. | `docs/deployment-render.md` → "Current state" |
| `render.yaml` Blueprint | A **separate, brand-new install** only. Its PostgreSQL 16, generated secret and new-owner steps do **not** apply here. | `render.yaml` (do not apply it to this deployment) |

**Keep as they are:**
- the web service URL, its build and start commands, and its 10 settings;
- the owner account `alistair`;
- PostgreSQL 18 and the Django secret key on the web service;
- database storage for files;
- closed external database access.

**Do not create:** a new web service, a new database, Redis, a disk, an environment group, or a workspace
plan upgrade.

## Will starting the worker read any old receipts?

**No.**
- The web service refuses to queue a reading while it has no `ANTHROPIC_API_KEY`, and it has never had one.
  So no reading jobs can exist before the pilot.
- A worker only picks up **queued** jobs, or a job whose worker died mid-reading. **Failed jobs are never
  retried automatically**: reading again is always a new, explicit tap on "Read receipt automatically" or
  "Try reading again".

You can also see this for yourself:
- The worker prints **`Claimable at start: N job(s)`** in its log when it starts.
- `python manage.py receipt_jobs`, run in the worker's **Shell**, lists exactly what a running worker would
  send. It shows only job numbers, statuses, timings and tokens: never merchants, amounts or file names.
- The steps below start the worker **without** a key first. If anything were somehow queued, it would fail
  as "not configured" instead of being sent.

## A. Anthropic API: dedicated workspace, key and US$5 limit

Do this in the Anthropic Console (console.anthropic.com), signed in to your organisation:

1. **Settings → Workspaces → Create workspace**, named `Room by Room`.
   - Leave other workspaces and organisation budgets unchanged.
2. Open the `Room by Room` workspace → **Limits** (spend limit) and set the monthly spend limit to **US$5**.
3. **Settings → Billing:**
   - Check whether credits are needed. If you must buy credits, **check the minimum purchase first**. If it
     is more than US$5, stop and report the amount before buying.
   - Make sure **auto-reload / automatic top-up is OFF**.
4. **API keys → Create key** in the `Room by Room` workspace, named `room-by-room-pilot`.
   - Copy it once and keep it only in your password manager until step C.
   - **Never** paste it into chat, email, a document, Git or a terminal command.

**Model:** `claude-haiku-4-5-20251001` (pinned). List price is **US$1 per million input tokens and US$5 per
million output tokens**.
- A phone photo is resized to at most 1568 px and usually costs a few thousand input tokens plus under
  1,000 output tokens. That is roughly **US$0.005–0.01 per reading**.
- Five receipts, including a retry, should cost **a few cents**.
- These are estimates. The pilot measures the real figures, and the Console usage page is the
  authoritative bill.

## B. Render: create the receipt worker

**Before creating it:**
- Confirm the founder has approved the pilot spend.
- Confirm the dashboard shows **Starter** at about **US$7/month** for a background worker.
- If the quote differs, stop and report.

**New → Background Worker**, connected to repository `OperGo/Room_by_room`:

| Field | Value |
|---|---|
| Name | `room-by-room-receipts` |
| Project / environment | the existing **Room by Room** project (same workspace) |
| Region | **Frankfurt** (must match the database) |
| Branch | `sprint-2a`. Deploy the **reviewed handoff commit** named in the Sprint 2C report. |
| Runtime | Python |
| Build command | `pip install -r requirements.txt` |
| Start command | `python manage.py process_receipts --watch --interval 3` |
| Instance type | **Starter** (0.5c-512mb), **1 instance** |
| Auto-Deploy | **Off** |
| Shutdown delay | **90 seconds** (Settings → Shutdown delay, if it isn't offered during creation) |

**Worker environment.** Add these on the worker itself. A new environment group is **not** linked to the
web service automatically, so don't use one.

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.13.14` |
| `DJANGO_SECRET_KEY` | Use Render's **Generate** button. The worker never signs sessions, so it does not need the web service's value. **Do not** copy the web secret. |
| `DJANGO_DEBUG` | `0` |
| `DATABASE_URL` | The existing database's **Internal Database URL** (private; Database → Connect → Internal) |
| `PRIVATE_STORAGE_BACKEND` | `database` |
| `RECEIPT_EXTRACTOR` | `anthropic` |
| `RECEIPT_MODEL` | `claude-haiku-4-5-20251001` |
| `ANTHROPIC_API_KEY` | **Leave out for now.** It is added in step C after the check. |

The worker does **not** need `STATIC_MANIFEST`, `DJANGO_HTTPS` or `DJANGO_SECURE_COOKIES`, because it
serves no web pages.

Leave these optional tuning variables unset, so they keep their tested defaults:
- `RECEIPT_TIMEOUT_SECONDS` 60;
- `RECEIPT_LEASE_SECONDS` 180;
- `RECEIPT_RETRY_DELAY_SECONDS` 30.

The attempt limit is fixed in code at **2 per job**.

**Create** the worker, then wait for the deploy. In the worker's **Logs**, expect:

```
Automatic extraction not configured (ANTHROPIC_API_KEY / RECEIPT_MODEL); …
Claimable at start: 0 job(s)
Watching for receipt jobs. Press Ctrl+C to stop.
```

Then open the worker's **Shell** and run:

```
python manage.py receipt_jobs
```

Expect `Claimable now …: 0`. If it is not 0, **stop**: suspend the worker and report the output (it contains
no receipt content).

## C. Add the key privately, worker first, then the web service

1. **Worker → Environment → Add** `ANTHROPIC_API_KEY`, paste the value from your password manager, then
   **Save** and deploy.
   - The log should no longer say "not configured".
   - It should again show `Claimable at start: 0 job(s)`.
2. **Web service → Environment → Add** `ANTHROPIC_API_KEY` (the same value), then **Save** and **Manual
   Deploy**.
   - The web service only uses the key to decide that reading is available. The provider is called **only**
     by the worker.
3. Check `/healthz/` → `{"status": "ok"}`.
   - On the phone, a new receipt now shows **"Read receipt automatically"** instead of "not configured".

## D. The five pilot receipts

Use five representative receipts. Label them **R1–R5** in all notes; never share the receipts or photos
themselves.

| Label | Receipt type |
|---|---|
| R1 | Simple itemised purchase (several lines) |
| R2 | Itemised with **delivery** or a **discount** line |
| R3 | One purchase **split across two projects** (allocate items to different projects) |
| R4 | An **imperfect phone photo**: angled, creased or dim |
| R5 | Any other typical receipt (or a PDF invoice) |

For **each** receipt:

1. Upload it, then tap **Read receipt automatically**. Note the time.
   - The page shows "Waiting/Reading…", then reloads with the values.
2. **Check every value against the paper original:**
   - merchant, date and total;
   - each item's description and amount;
   - delivery and discount lines.
   Note how many values were right, and each correction you made (for example: "R2: total read 41.50, actual
   41.05").
3. **Before confirming:** open **Costs** and check that the total has **not** changed. A reading alone
   records nothing.
4. Allocate the items to projects (for R3, across two projects).
5. **Once per pilot** (on any receipt): set a **wrong total** and confirm.
   - Expect "Nothing was recorded…" with your entries kept.
   - Then correct the total.
6. **Confirm purchase** once.
   - Check that Costs and each project show exactly the right amounts, to the penny.
7. **Once per pilot:** go back in the browser and press Confirm again (or double-tap).
   - Expect the same purchase, not a second one, and totals unchanged.
8. **Once per pilot:**
   - Copy an "Open original" link.
   - Sign out from **Home → bottom → Sign out**.
   - Open the link in the same browser. Expect the sign-in page.

**Failure check (once).** In a **separate private window**, upload a photo that is **not a receipt** (for
example a blank page) and tap Read.
- Expect either a failure message ("Couldn't read this receipt") with manual entry still available, or a
  flagged, mostly empty reading.
- Either way, **nothing is recorded**, and Costs is unchanged.

**After all five.** In the worker's **Shell**, run `python manage.py receipt_jobs` and copy the output into
your reply. It lists, per job:
- attempts;
- queue-to-finish and reading time;
- model;
- input/output tokens;
- the estimated list-price cost.

**Stop immediately and report** if any of these happen:
- the Anthropic Console shows spend near **US$5**;
- any job shows **more than 2 attempts**, or keeps retrying;
- jobs appear that you did not request;
- the Render bill shows more than the quoted worker.

## E. When the pilot is finished (unless continuation is approved)

1. In the Anthropic Console, **disable or delete** the `room-by-room-pilot` key.
2. Render → **web service → Environment**: delete `ANTHROPIC_API_KEY`, then Save and Manual Deploy. The
   app then shows "Automatic extraction not configured" again, and manual entry continues.
3. Render → **worker → Settings → Suspend**. Check that the worker shows **Suspended**, and that **Billing**
   shows no further worker charges beyond the days it ran. Render bills paid instances by the second.
4. Report the following:
   - per receipt: the R1–R5 accuracy notes and corrections;
   - the `receipt_jobs` output;
   - the Console's actual spend;
   - the worker's status and billing.

## Afterwards: durable hosting (separate approval)

If the pilot is useful, the proposal is to upgrade the **existing** web service and PostgreSQL 18 database
in place before **2 November 2026**, keeping one worker. That is about **US$20.30/month before tax**, API use
and overages. It needs separate founder approval; see `docs/deployment-render.md`.
