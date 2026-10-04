# Milestone 1: affordable runtime and persistence decision (5 October 2026)

**Status:** recommendation prepared. **Nothing approved, bought, created or deployed.** Applying it needs the
founder's explicit approval and a check of the Render dashboard quotes (checklist at the end).

## Recommendation

| Part | Setup | Monthly cost (USD, before tax) |
|---|---|---|
| Receipt reading | One **Render Cron Job**, Starter, Frankfurt, running the existing `python manage.py process_receipts --once` **every minute** | **US$1.00 minimum; about US$1.20–3.50 expected** (billed by the second) |
| Database | **Upgrade the existing free PostgreSQL 18 in place** to the paid `0.1c-256mb` plan, 1 GB storage. Data, URL and owner are kept, and it never expires. Paid databases include Render's managed backups. | **US$6.00 + US$0.30 storage** |
| Web service | **Keep the existing free web service.** Decide in milestone 3 whether its sleep after 15 minutes is too much friction (Starter would add US$7). | US$0 |
| API | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) in a dedicated Anthropic workspace with a monthly spend limit | about **US$0.0075 per receipt**; for example about US$0.75 for 100 receipts. Limit US$5/month. |
| **Total** | | **about US$8.50–11 per month** plus tax and API use (about US$15 with a Starter web service) |

Compare: a dedicated background worker costs US$7/month on its own. The full paid plan (paid web service,
worker and database) costs about US$20.30/month.

## Why a Cron Job, and how it behaves

Facts from Render's documentation (search extracts of render.com/docs/cronjobs, /pricing and related
articles, October 2026):
- Cron Jobs are **billed by the second of active running time**, with a **US$1/month minimum** per cron job.
- Every run starts a **fresh container** and stops when the command exits.
- **At most one run is active at a time.** If a run is still going when the next is due, the next run is
  delayed, not run in parallel.
- Runs are stopped after 12 hours.
- Schedules are evaluated in **UTC**.

**Uses the existing code unchanged.** `process_receipts --once` claims every claimable job (oldest first),
reads each one, records the result and exits. Each run logs `Claimable at start: N job(s)` and
`Processed N job(s).` (the start-up count is capped at 20).

Everything that matters stays in the database, not in the runtime:
- persisted jobs and leases;
- owner-scoped drafts;
- private files in database storage;
- results applied only to an unchanged draft;
- review and confirmation before any cost is recorded.

There are **no background threads** in the web service.

### Waiting time

From tapping "Read receipt automatically" until the values appear:
- up to **60 s** for the next scheduled minute (about 30 s on average);
- **plus container and Python start-up**: about 3 s locally on a cold start (0.5 s warm). On Render's 0.5-CPU
  Starter this is estimated at 10–20 s and is **unmeasured** until milestone 2;
- **plus the reading itself**: estimated 5–15 s, also unmeasured.

So expect **typically about 1 minute, at worst about 2 minutes.** The review page checks every 3 seconds and
fills in the values automatically. The owner can keep typing meanwhile; typed values are never overwritten.

**Known cosmetic issue (for milestone 3):** after 120 s in the queue, the page shows "Still waiting. The
receipt worker may not be running". With a once-a-minute schedule, a slow cold start could occasionally
trigger that wording even though nothing is wrong. Fixing it would be a one-line threshold or wording change,
held for milestone 3.

### Retries and recovery (rehearsed locally; see `docs/sprints/evidence/milestone-1-cron-rehearsal.txt`)

- **Retryable provider error** (timeout, connection, 429/5xx): the job waits 30 s, then the next run after that
  retries it. That is **attempt 2 of 2**, at most. Rehearsed: the run before the delay ended skipped it, and a
  later run succeeded on attempt 2.
- **Permanent error** (refusal, malformed output, authentication): the job fails at once. It is **never
  retried automatically**; reading again is an explicit owner action, and manual entry stays available.
- **A run killed mid-reading** (deploy, restart, platform stop): the job keeps its 180 s lease, so the next
  runs leave it alone. After the lease expires, a run recovers it (attempt 2), or marks it failed if no
  attempts are left, without calling the provider. Rehearsed with SIGKILL: run 2 skipped it, and run 3
  recovered and applied it on attempt 2.
- **Overlapping runs** (normally prevented by Render): each job is claimed once
  (`SELECT … FOR UPDATE SKIP LOCKED`). Rehearsed: two simultaneous runs took one job each.
- **No reading records a cost.** Rehearsed: the purchase count was unchanged.

### Cost workings (cron)

Assumptions:
- **Rate:** a Starter cron instance is priced like other Starter instances, US$7 per 30-day month, which is
  about **US$0.0000027 per second** (US$0.00016 per minute). **Confirm the exact rate on the dashboard before
  approving.**
- **Schedule:** every minute, 24/7, which is 43,200 runs per 30-day month.
- **Idle run:** billed for start-up plus one query and exit.

| Billed seconds per idle run | Monthly runtime | Cost | Bill (minimum US$1) |
|---|---|---|---|
| 5 s | 60 h | US$0.58 | **US$1.00** |
| 10 s | 120 h | US$1.17 | **US$1.17** |
| 20 s | 240 h | US$2.33 | **US$2.33** |
| 30 s | 360 h | US$3.50 | **US$3.50** |

- **Reading time:** under 1 cent per month. For example, 100 receipts × 15 s = 25 minutes, about US$0.004.
- **Builds** happen only on manual deploys. Check that Render's included build minutes cover them.
- **Cheaper option if needed:** run only during waking hours, for example `* 6-22 * * *` (06:00–22:59 UTC).
  That is about 30% fewer runs (17 of 24 hours). Readings requested overnight then wait until 06:00 UTC.
- **Stop condition:** after the first 24 hours, check the cron job's usage on Render's Billing page. If it
  extrapolates above **US$5/month**, change the schedule to every 2 minutes or waking hours only, or move to
  the fallback.

### API cost workings

- Haiku 4.5 list price: US$1 per million input tokens and US$5 per million output tokens.
- A receipt photo, resized to at most 1568 px, plus the extraction instructions is about 4,000 input tokens.
  The structured reading is about 700 output tokens.
- That is **about US$0.0075 per receipt** (estimate). A retry can at most double it.
- The workspace **spend limit** caps the total.
- Real figures are measured in milestone 2 with `python manage.py receipt_jobs`. If the cron job offers no Shell,
  milestone 2 will use the per-run log lines, or run `receipt_jobs` via a one-off job.

### Persistence

- The free database **expires on 2 November 2026** and has no backups. Real records from everyday use need
  retained data.
- **Upgrading it in place** (Free → `0.1c-256mb`, keeping PostgreSQL 18) keeps everything already in it,
  removes the expiry and adds Render's managed backups. This retires the manual-backup question.
- Recommended **when the cron job is approved (milestone 2)**, so the five live receipts and the everyday use
  that follows are retained.

## Fallback (only if needed)

If, in milestone 2, the cron start-up makes waiting too long or the billing extrapolates too high, use the
already-prepared **Starter background worker** (`docs/receipt-pilot.md`):
- it is always running and checks every 3 s, so a reading takes about 10–20 s;
- it costs US$7/month flat (total about US$14 plus tax and API use with the free web service);
- nothing else changes.

## Founder approval checklist (apply only after explicit approval)

Before step 1, confirm on the dashboards:
- the cron job's Starter rate;
- the database `0.1c-256mb` quote (about US$6.30);
- the Anthropic minimum credit purchase. If it is more than the spend limit, report it before buying.

1. **Anthropic Console:**
   - create a `Room by Room` workspace;
   - set a monthly **spend limit of US$5**;
   - make sure **auto-reload is off**;
   - create a key named `room-by-room`, kept only in your password manager. Do not change other workspaces or
     budgets.
2. **Render → database → Upgrade instance type:**
   - choose **0.1c-256mb** and keep **PostgreSQL 18**;
   - confirm the quote;
   - afterwards check that the web service `/healthz/` is `{"status": "ok"}` and your data is still there.
3. **Render → New → Cron Job** (repository `OperGo/Room_by_room`):
   - Region: **Frankfurt**. Project: the existing **Room by Room**.
   - Branch: `sprint-2a`, at the reviewed handoff commit.
   - Schedule `* * * * *`.
   - Build command `pip install -r requirements.txt`. Command `python manage.py process_receipts --once`.
   - Instance type **Starter**. Auto-Deploy **Off**.
   - Environment, set on the cron job itself:

     | Key | Value |
     |---|---|
     | `PYTHON_VERSION` | `3.13.14` |
     | `DJANGO_SECRET_KEY` | Render **Generate**. Do not copy the web secret. |
     | `DJANGO_DEBUG` | `0` |
     | `DATABASE_URL` | the database's **Internal** URL (private) |
     | `PRIVATE_STORAGE_BACKEND` | `database` |
     | `RECEIPT_EXTRACTOR` | `anthropic` |
     | `RECEIPT_MODEL` | `claude-haiku-4-5-20251001` |

   - **Do not add the key yet.**
4. Create the cron job, wait for its first scheduled run (or press **Trigger Run**) and read its **Logs**.
   Expect `Automatic extraction not configured …` and `Claimable at start: 0 job(s)`. If any job is listed,
   suspend the cron job and report.
5. **Cron job → Environment:** add `ANTHROPIC_API_KEY` (from your password manager) and save. The next run's
   log should no longer say "not configured".
6. **Web service → Environment:** add `ANTHROPIC_API_KEY` (same value), save, then **Manual Deploy**. Check
   `/healthz/`.
7. Read one receipt on the phone and note how long the values take to appear. The five-receipt protocol is
   milestone 2.
8. **After 24 hours:** Render Billing → the cron job's usage. Extrapolate a month. Above US$5, apply the stop
   condition above.

**Rollback** at any point:
- suspend the cron job;
- delete `ANTHROPIC_API_KEY` from the web service and Manual Deploy (manual entry continues);
- disable the key in the Anthropic Console.

The database upgrade does not need rolling back.
