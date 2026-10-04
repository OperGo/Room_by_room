ROOM BY ROOM — MILESTONE 1 (AFFORDABLE RUNTIME AND PERSISTENCE DECISION) REPORT TO CHATGPT CTO
Date: 5 October 2026
Current milestone: 1 of 5 (due 5 October), complete as a recommendation. Founder approval is needed before milestone 2.
Status: one recommended setup, a cost model, a local synthetic rehearsal and a founder-applied approval checklist are prepared (docs/receipt-runtime-decision.md). No paid resources, API keys, live calls or deployments. No application code changed.

1. OUTCOME
Recommended setup:
- Receipt reading: a Render Cron Job (Starter, Frankfurt, existing project) running the existing `python manage.py process_receipts --once` every minute (`* * * * *`). Billed by the second, US$1/month minimum; about US$1.20–3.50 expected.
- Persistence: upgrade the existing free PostgreSQL 18 in place to 0.1c-256mb (1 GB) at US$6.30/month. It keeps the data, URL and owner, removes the 2 November expiry and adds managed backups. Recommended at milestone 2 approval, so live receipts and everyday use are retained.
- Web: keep the existing free web service. Its 15-minute sleep is a milestone 3 friction decision (Starter would add US$7).
- API: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) in a dedicated Anthropic workspace with a US$5 monthly limit and auto-reload off. Estimated cost about US$0.0075 per receipt.
- Complete bill: about US$8.50–11/month before tax and API use (about US$15 with a Starter web service), versus about US$20.30 for the dedicated-worker paid plan.
Waiting time (estimated): up to 60 s for the next minute, plus cold start (10–20 s estimated on Render, 3.3 s measured locally), plus reading (5–15 s estimated). Typically about 1 minute, at worst about 2. The page polls every 3 s and fills the values in automatically; owner typing is never overwritten.
Retry and recovery: unchanged and rehearsed.
- A retryable error is retried by a later run after 30 s, at most 2 attempts.
- Permanent failures are never retried automatically; manual entry remains.
- A killed run's job is recovered after its 180 s lease expires, or failed without a provider call if its attempts are used up.
- Overlapping runs cannot claim the same job (Render runs one at a time, and the claim uses SKIP LOCKED).
Fallback (one): the already-prepared Starter background worker (docs/receipt-pilot.md, now marked as the fallback). US$7/month flat, reading in about 10–20 s. Use it only if milestone 2 shows cron waits or billing worse than estimated.

2. SCOPE
Delivered:
- docs/receipt-runtime-decision.md: recommendation, Render cron facts with sources, waiting-time, retry/recovery and cost workings, persistence, fallback, an 8-step approval checklist and rollback.
- docs/deployment-render.md overview row; docs/receipt-pilot.md marked as the fallback.
- Guard test for the new checklist.
- Rehearsal evidence: docs/sprints/evidence/milestone-1-cron-rehearsal.txt.
Deferred/incomplete, with reasons: everything paid or live (not approved). The real Render cold-start time, per-run billed seconds and per-receipt tokens are measured in milestone 2.
Departures from CTO brief, with reasons: none. No background threads, no rewrite; persisted jobs, owner protection, private files, bounded retries and review-before-confirmation are unchanged.

3. CODE AND SETUP
- Branch sprint-2a; documentation and test only (no application change).
- Pushed normally; the final SHA and verified remote HEAD are given in the handoff message.
- No PR, merge or deploy.
Cron job settings (founder-applied after approval):
- schedule `* * * * *`; build `pip install -r requirements.txt`; command `python manage.py process_receipts --once`;
- Starter, Frankfurt, Auto-Deploy Off, branch sprint-2a at the handoff commit.
- Environment: PYTHON_VERSION=3.13.14; DJANGO_SECRET_KEY (Generate); DJANGO_DEBUG=0; DATABASE_URL (Internal, private); PRIVATE_STORAGE_BACKEND=database; RECEIPT_EXTRACTOR=anthropic; RECEIPT_MODEL=claude-haiku-4-5-20251001.
- ANTHROPIC_API_KEY is added only after the first run logs "Claimable at start: 0 job(s)": first on the cron job, then on the web service (Manual Deploy).

4. VALIDATION
Checks actually run and results:
- Idle `--once` runtime with production settings on PostgreSQL 18.6: cold 3.29 s, warm 0.49–0.55 s (this machine). Render's figure is unmeasured.
- Synthetic cron-cadence rehearsal (fake extractor, PG 18.6, each run a separate process):
  - A: request-to-result 13.5 s with a 6 s simulated reading.
  - B: a retryable timeout; the run inside the retry delay claimed nothing; a later run succeeded on attempt 2 of 2.
  - C: a run killed with SIGKILL mid-reading; the next run skipped the leased job; after lease expiry a run recovered it and applied it on attempt 2.
  - D: two simultaneous runs processed one job each.
  - The purchase count was unchanged (1 before, 1 after).
- Tests: `pytest tests/test_free_preview_config.py tests/test_reading_jobs.py` → 38 passed. No full-suite rerun: no application code changed.
- Render facts from search extracts of render.com/docs/cronjobs, /pricing and related articles (render.com is blocked from this environment):
  - per-second billing with a US$1 minimum;
  - a fresh container per run;
  - at most one active run;
  - a 12-hour maximum;
  - UTC schedules.
  The exact Starter cron per-minute rate was not shown. The plan assumes US$0.00016/min (the same as US$7 per 30-day month), and the founder confirms it on the dashboard.
Not verified: the Render cron cold start and billed seconds, the live API, and the dashboard quotes.

5. COST INTEGRITY
Unchanged. Readings never record costs; confirmation remains transactional, version-checked and idempotent.

6. RECEIPT PROCESSING
Unchanged adapter (anthropic==1.11.0, Haiku 4.5, structured output, at most 2 attempts). It is tested with a mocked SDK only; live accuracy is unproven.

7. RISKS / DECISIONS FOR CTO
Acceptance evidence for milestone 1: the recommendation, cost model, rehearsal transcript and checklist above.
Remaining launch blockers:
- the founder's approval of the spend (cron job, database upgrade, API limit);
- milestone 2's five live receipts through to accurate confirmed costs;
- everyday-use friction fixes (milestone 3), including the 120 s "worker may not be running" wording under a cron cadence and the free web service's cold starts;
- retained-data readiness (milestone 4).
Estimated remaining effort:
- milestone 2: about 1.5–2 h founder plus about 3 h Claude;
- milestone 3: 2–3 days of founder use plus about 4–8 h fixes;
- milestone 4: about 2–3 h;
- milestone 5: about 2 h.
Effect on the 16 October target: on track if the founder approves by 6 October. Approval later than about 8 October compresses milestone 3.
Risks:
- Render cold starts longer than estimated would lengthen waits and raise cron cost; the stop condition after 24 h triggers the schedule change or the fallback.
- The minimum Anthropic credit purchase is unknown until the founder checks.

8. FOUNDER REVIEW
Read docs/receipt-runtime-decision.md. If you approve, confirm the dashboard quotes and follow the checklist. Milestone 2 then begins with the five live receipts. Reply with your approval, or with which part you would change.
