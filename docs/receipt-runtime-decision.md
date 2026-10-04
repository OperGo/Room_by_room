# Receipt runtime and persistence: decision and Milestone 2 setup

Milestone 1 recommendation, accepted by the CTO on 5 October 2026; preflight corrections applied.

**Status:** nothing has been approved, bought, created or deployed. Applying this needs:
- the founder's **explicit budget approval**;
- a check of the **actual dashboard quotes** (checklist below).

## Recommendation

| Part | Setup | Monthly cost (USD, before tax) |
|---|---|---|
| Receipt reading | One **Render Cron Job**, Starter, Frankfurt, running the existing `python manage.py process_receipts --once` **every minute** | Billed by the second at Render's published **US$0.00016 per minute**, with a US$1 minimum: **about US$1.15–3.46** (see workings) |
| Database | **Upgrade the existing free PostgreSQL 18 in place** to `0.1c-256mb` with 1 GB storage. It keeps the data, URL and owner, no longer expires, and gets Render's managed backups. | **US$6.00 + US$0.30 storage = US$6.30** |
| Web service | **Keep the existing free web service.** Paid web would add **US$7** and needs separate approval (Milestone 3 decision). | US$0 |
| **Infrastructure total** | | **about US$7.50–9.80 per month**, before tax and API usage |
| API | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) in a dedicated Anthropic workspace | about **US$0.0075 per receipt** (estimate); see the spending boundaries below |

## How the Cron Job behaves

Facts from Render's documentation (render.com/docs/cronjobs and /pricing, October 2026):
- billing is **by the second of active running time**, at US$0.00016 per minute for Starter, with a **US$1/month
  minimum** per cron job;
- every run starts a **fresh container**;
- **at most one run is active at a time**; a late run is delayed, never run in parallel;
- runs are stopped after 12 hours;
- schedules are evaluated in **UTC**;
- **manually triggering a cron job while a run is active cancels that run**, so don't press Trigger Run while a
  run is in progress.

The application code is the existing code. `process_receipts --once` claims all claimable jobs (oldest
first), reads each one, records the result and exits. It logs `Claimable at start: N job(s)` (the count is
capped at 20) and `Processed N job(s).`

Unchanged protections:
- persisted jobs and leases;
- owner scoping;
- private files in database storage;
- results applied only to an unchanged draft;
- at most 2 attempts per job;
- review and confirmation before any cost is recorded;
- no background threads in the web service.

### Waiting time

**Ordinary first-attempt target: roughly 1–2 minutes** from tapping "Read receipt automatically" to the values
appearing. That is made up of:
- the wait for the next scheduled minute (0–60 s);
- container and Python start-up: 3.3 s measured locally on a cold start, estimated 10–20 s on Render;
- the reading itself: estimated 5–15 s.

Render's start-up and reading times are **measured in Milestone 2**. The review page checks every 3 s and fills
in the values automatically; the owner can keep typing meanwhile, and typed values are never overwritten.

**It can take longer:**
- a **retry** happens on the first run at least 30 s after an error;
- a **backlog** of several receipts is read one after another in the same run;
- **recovery** after a run is killed waits for the 180 s lease to expire, then the next run.

**Waiting message (corrected for Milestone 2):** the page now says "Still waiting. Readings normally start
within 1–2 minutes…" only after **5 minutes** in the queue. Before, it said "the receipt worker may not be
running" after 120 s, which an ordinary cron cycle could trigger. Covered by a focused test.

### Retries and recovery

Rehearsed locally; see `docs/sprints/evidence/milestone-1-cron-rehearsal.txt`.
- **Retryable** error (timeout, connection, 429/5xx): retried by a later run after 30 s, at most 2 attempts in
  total.
- **Permanent** error: fails at once and is **never retried automatically**. Manual entry stays available.
- **Killed run:** the job is recovered after its lease expires, or marked failed without a provider call if its
  attempts are used up.
- **Overlapping runs** cannot claim the same job (`SKIP LOCKED`).
- **Reading records no cost.**

### Cron cost workings

Every minute, 24/7, is **43,200 runs per 30-day month**. Each idle run is billed for start-up, one query and
exit. Reading time adds under 1 cent a month: 100 receipts × 15 s = 25 minutes ≈ US$0.004.

| Billed seconds per idle run | Billed minutes per month | Cost at US$0.00016/min | Bill (minimum US$1) |
|---|---|---|---|
| 5 s | 3,600 | US$0.58 | **US$1.00** |
| 10 s | 7,200 | US$1.15 | **US$1.15** |
| 20 s | 14,400 | US$2.30 | **US$2.30** |
| 30 s | 21,600 | US$3.46 | **US$3.46** |

The expected range is 10–30 s per idle run. With the database at US$6.30, that gives **US$7.45–9.76**, rounded
to US$7.50–9.80.

**Builds** happen only on manual deploys and are covered by Render's included build minutes; check this on the
dashboard.

**Cheaper schedule if needed:** waking hours only, for example `* 6-22 * * *` (06:00–22:59 UTC), cuts runs by
about 30%. Readings requested overnight then wait until 06:00 UTC.

## Spending boundaries

All of these need the founder's approval first.

| Boundary | Value | Kind |
|---|---|---|
| Cron Job | Starter, every minute | **Monitoring threshold, not a billing cap.** After the first 24 hours, if Render's usage projects **more than US$5/month** for the cron job, **suspend it and report**. Render keeps billing by the second while it runs. |
| Database | 0.1c-256mb, 1 GB, about US$6.30/month | **Keeps billing even if the cron trial stops.** Suspending the cron job does not stop database charges. |
| Anthropic monthly workspace limit | **US$5 per month** (spend limit on the `Room by Room` workspace) | A hard limit enforced by Anthropic for that workspace each month |
| **Total API testing allowance (Milestone 2)** | **US$5 in total**, tracked across all testing on the Console's usage page, separately from the monthly limit | If cumulative testing spend reaches the allowance, stop and report, even if the monthly limit has not been reached |
| Credits | Buy only what is needed. **Auto-reload off.** | If the minimum purchase is above the allowance, report before buying. |
| Not approved by this plan | A dedicated background worker (US$7/month) or a paid web service (US$7/month) | Each needs **separate approval** |

**Backups:** the paid database's managed backups do **not** replace Milestone 4's recovery check before relying
on important records. The founder's no-manual-backup decision still stands for the disposable preview.

## Founder setup checklist (apply only after explicit approval)

**Before starting**, confirm on the dashboards and report any difference:
- the cron job's Starter rate (US$0.00016/minute);
- the database `0.1c-256mb` quote (about US$6.30);
- the Anthropic minimum credit purchase.

**Final tested SHA:** deploy the **handoff SHA named in the Milestone 1 preflight report** (branch `sprint-2a`),
on **both** the cron job and the web service.

1. **Anthropic Console:**
   - create a `Room by Room` workspace;
   - set the **monthly spend limit to US$5**;
   - make sure **auto-reload is off**;
   - buy credits only if needed (minimum purchase, at most the allowance);
   - create the key `room-by-room` and keep it only in your password manager.
   Do not change other workspaces or budgets.
2. **Render → database → Upgrade instance type:**
   - choose `0.1c-256mb` and keep **PostgreSQL 18**;
   - confirm the quote;
   - afterwards check that `/healthz/` shows `{"status": "ok"}` and your data is still there.
3. **Render → New → Cron Job** (repository `OperGo/Room_by_room`):
   - Region **Frankfurt**; project **Room by Room**.
   - Branch `sprint-2a` at the final tested SHA.
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
4. Create the cron job and wait for its first **scheduled** run. Don't press Trigger Run while a run is active.
   - Its **Logs** should show `Automatic extraction not configured …` and `Claimable at start: 0 job(s)`.
   - If any job is listed, suspend the cron job and report.
5. **Activate the key on the cron job:**
   1. Cron job → **Environment** → add `ANTHROPIC_API_KEY`.
   2. Choose **"Save, rebuild, and deploy"** (or "Save and deploy"). **"Save only" does not apply it to the next
      run.**
   3. Wait for the deploy to finish.
   4. The next scheduled run's log should no longer say "not configured".
6. **Activate the key on the web service:**
   1. Web service → **Environment** → add `ANTHROPIC_API_KEY` (same value).
   2. Choose **"Save, rebuild, and deploy"**, or "Save only" followed by **Manual Deploy → Deploy latest
      commit**.
   3. Confirm that the deployed commit is the **final tested SHA**.
   4. Check that `/healthz/` shows `{"status": "ok"}`.
   This deploy also delivers the corrected waiting message.

**Rollback** at any point:
- **suspend** the cron job;
- delete `ANTHROPIC_API_KEY` from the web service and Save and deploy (manual entry continues);
- disable the key in the Anthropic Console.

The database keeps billing; it does not need rolling back.

## Milestone 2 evidence protocol (five live receipts)

Label the receipts **R1–R5** and never share the receipts themselves. Aim for **at least four useful drafts from
legible samples**:

| Label | Receipt type |
|---|---|
| R1 | itemised |
| R2 | delivery or discount |
| R3 | split across two projects |
| R4 | an imperfect phone photo |
| R5 | typical (or a PDF) |

For each receipt, record:
- **request-to-result time**: from tapping Read to the values appearing;
- the **values checked** against the paper (merchant, date, total, each line), and **each correction**.

**Once across the five receipts**, check each of these:
1. Before confirming, Costs is unchanged: **reading records no purchase**.
2. A **wrong total is refused** ("Nothing was recorded…") with your entries kept.
3. After the **corrected confirmation**, Costs and each project are **exact to the penny**.
4. Going back and confirming again **does not double-count**.
5. **Private files:** copy an "Open original" link, sign out (Home → Sign out), open the link in the same
   browser, and expect the sign-in page.
6. **Provider failure:** in a private window, upload a non-receipt photo and tap Read. Expect a failure or a
   mostly empty flagged reading, with **manual entry still available** and **nothing recorded**.

### Collecting the `receipt_jobs` evidence (attempts, model, tokens, timings)

The ordinary run logs don't include token figures. Use the existing read-only `receipt_jobs` command.

**If the cron job offers a Shell:** open it and run `python manage.py receipt_jobs --limit 20`.

**If there is no Shell,** temporarily swap the cron command:
1. **Pause uploads.** Don't upload or tap Read during this procedure.
2. On the cron job's **Runs/Events** page, **wait until no run is active**, and the last run shows finished.
   Don't press Trigger Run during an active run: Render cancels it.
3. Cron job → **Settings → Command:** change it to `python manage.py receipt_jobs --limit 20`, then save and
   deploy.
4. Wait for the next **scheduled** run, then copy its **Logs** output. It contains only job numbers, statuses,
   attempts, timings, model, tokens and the estimated cost; never merchants, amounts or file names.
5. Change the command back to `python manage.py process_receipts --once`, then save and deploy.
6. Confirm that the next scheduled run logs `Claimable at start: …`. Then resume uploads.

No extra diagnostic service and no database credentials are needed, and nothing is pasted into chat except
that sanitised output.

**Also collect:**
- **Actual API spend:** Anthropic Console → Usage, for the `Room by Room` workspace.
- **Actual cron usage after 24 hours:** Render → Billing (or the cron job's usage). Project a month from it and
  apply the US$5/month monitoring threshold.

## Fallback (separate approval)

If Milestone 2 shows cron waits or billing worse than estimated, the prepared fallback is the **Starter
background worker** (`docs/receipt-pilot.md`):
- it reads in about 10–20 s;
- it costs US$7/month;
- it **needs separate approval**.
