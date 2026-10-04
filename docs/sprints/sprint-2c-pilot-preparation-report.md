ROOM BY ROOM — SPRINT 2C (LIVE RECEIPT PILOT) PREPARATION REPORT TO CHATGPT CTO
Date: 4 October 2026
Status: the no-cost preparation is complete and pushed. Nothing has been bought, created or deployed, and no API call has been made. The pilot needs explicit founder approval of the budget and a check of the Render dashboard quote before step A of the checklist. First-release acceptance is not claimed: live extraction through to accurate confirmed costs remains unproven.

1. OUTCOME
- docs/receipt-pilot.md is one founder-applied checklist. It covers:
  A. A dedicated Anthropic "Room by Room" workspace, a US$5 spend limit, auto-reload off, a minimum-purchase check and a named pilot key.
  B. One Render background worker:
     - Frankfurt, existing project, Starter (0.5c-512mb), 1 instance;
     - manual deploys; build `pip install -r requirements.txt`; start `python manage.py process_receipts --watch --interval 3`;
     - shutdown delay 90 s; branch sprint-2a at the reviewed handoff commit;
     - the worker environment listed explicitly (below).
  C. The key added privately on the worker first (after the empty-queue check), then on the existing web service.
  D. The five-receipt protocol with evidence capture, the failure check and the stop conditions.
  E. Close-down: disable the key, remove it from the web service, suspend the worker, verify status and billing.
- Old receipts cannot be sent unannounced:
  - The web service refuses to queue readings without a key and has never had one, so no jobs can exist.
  - Failed jobs are never re-claimed. Claim criteria are now one shared function, `claimable_jobs()`.
  - The worker logs "Claimable at start: N job(s)" when it starts.
  - The new read-only `python manage.py receipt_jobs` (worker Shell) lists exactly what a running worker would send.
  - The checklist starts the worker without a key first, so any stray job fails as "not configured" instead of being sent.
- Found and fixed during rehearsal: the worker's log lines were block-buffered on a pipe (as on Render), so "Claimable at start" did not appear until exit. Each line is now flushed.
- docs/deployment-render.md now separates four things: the live free preview, the pilot, the proposed in-place upgrade (existing web service and PG18 database; US$20.30/month; separate approval before 2 November), and render.yaml. render.yaml is marked NEW-INSTALL ONLY; its PG16, generated-secret and new-owner assumptions do not govern this deployment.
- The founder's no-backup decision for the disposable preview is recorded in the guide as deliberate and CTO-accepted.

2. SCOPE
Delivered:
- apps/receipts/jobs.py: claimable_jobs() and a shared claim filter, with no behaviour change.
- process_receipts: start-up claimable-jobs line and flushed log lines.
- receipt_jobs command (read-only metadata):
  - claimable jobs; per job: status, result, attempts, queue-to-finish and last-attempt seconds, model, input/output tokens, error code, and an 8-character receipt reference;
  - a list-price cost basis (Haiku 4.5: US$1/US$5 per million tokens);
  - never merchants, amounts, file names or provider output.
- Guides: receipt-pilot.md (new), deployment-render.md, deployment-render-free-preview.md, receipt-processing.md, render.yaml header.
Deferred/incomplete, with reasons: the pilot itself (approval and spend are not authorised yet).
Departures from CTO brief, with reasons:
- The worker gets its own Render-generated DJANGO_SECRET_KEY rather than a copy of the web secret. It never signs sessions, and this avoids handling the web secret. The web secret is unchanged.
- The worker deliberately omits STATIC_MANIFEST, DJANGO_HTTPS and DJANGO_SECURE_COOKIES: it serves no pages.

3. CODE AND SETUP
Repository path, branch, commit(s), remote/PR only if actually created:
- /home/user/Room_by_room, branch sprint-2a.
- 15f32d3: preparation; 53edb47: backup decision; then this report commit.
- Pushed normally; the final remote SHA is verified against HEAD in the handoff message. That SHA is the reviewed handoff commit for the worker, and for the web redeploy when its key is added.
- No PR, merge, deployment, Render or Anthropic change.
Worker environment (on the worker itself, not an environment group):
- PYTHON_VERSION=3.13.14;
- DJANGO_SECRET_KEY: Render "Generate";
- DJANGO_DEBUG=0;
- DATABASE_URL: the existing database's Internal URL (private);
- PRIVATE_STORAGE_BACKEND=database;
- RECEIPT_EXTRACTOR=anthropic; RECEIPT_MODEL=claude-haiku-4-5-20251001;
- ANTHROPIC_API_KEY: private, added only in step C.
Web service: unchanged except ANTHROPIC_API_KEY (private, step C), then a Manual Deploy. URL, owner, PG18, secret, commands, closed external access and file storage are all preserved.
Exact commands:
  python manage.py receipt_jobs            (read-only; worker Shell)
  python manage.py process_receipts --watch --interval 3
  pytest ; DATABASE_URL=postgres://… pytest   (PostgreSQL 16.14 and 18.6)

4. VALIDATION
Checks actually run and results:
- SQLite: `pytest` → 256 passed, 8 skipped.
- PostgreSQL 16.14: 264 passed. A first run errored because the local server had stopped (container restart); after a restart, 264 passed.
- PostgreSQL 18.6 (the deployed major version): 264 passed.
- 5 new test functions. [Corrected in the Sprint 2C closeout: the original report said "7 new tests"; the
  reviewed diff adds five test functions.]
  - only queued/due jobs are claimable, and a permanently failed job is never claimable again;
  - receipt_jobs reports tokens and the list-price cost (2000/600 tokens → US$0.0050) and leaks no merchant, file name or amount;
  - the worker announces claimable jobs at start;
  - worker log lines are flushed;
  - the pilot checklist contains the exact worker fields, settings, empty-queue check, US$5 limit and auto-reload off, with no credentials, and render.yaml carries the NEW-INSTALL ONLY marker.
- Real-process rehearsal on the PostgreSQL 18.6 stand-in, using pilot settings (DEBUG off, database storage, RECEIPT_EXTRACTOR=anthropic, no key, the exact start command):
  - receipt_jobs before the worker: claimable 0.
  - A deliberately stray queued job: the worker log showed, live, "Automatic extraction not configured…", "Claimable at start: 1 job(s) (ids [2])", "Watching…" and "Processed 1 job(s)".
  - The job ended failed with not_configured, 0 tokens, nothing sent.
  - SIGTERM → "Stopped.", exit 0.
  - receipt_jobs afterwards: claimable 0.
- Anthropic facts: from the bundled Claude API model reference (cached 25 September 2026), `claude-haiku-4-5-20251001` is an active snapshot at US$1/US$5 per million input/output tokens. Workspace spend limits exist. The minimum credit purchase is not documented there, so the founder must check it.
Screens inspected and viewport widths: not applicable (no UI change).
Actual screenshots: none.
Failed tests, untested behaviour and limitations:
- No live provider call, no Render worker and no hosted check; all need approval.
- Live accuracy, latency and real token usage are unmeasured.
- The Render dashboard labels (Shutdown delay, Shell, Suspend) come from earlier research; the founder confirms them in the dashboard.

5. COST INTEGRITY
No change to money logic. The pilot protocol checks that:
- reading alone records nothing;
- a wrong total is refused with entries kept;
- a confirmation counts once, to the penny across projects;
- a repeated confirmation cannot double-count.

6. RECEIPT PROCESSING
- Real adapter: AnthropicExtractor (anthropic==1.11.0, structured output, images ≤1568 px, PDFs as documents, SDK retries off, at most 2 attempts per job, 60 s timeout). It remains tested only with a mocked SDK.
- Live samples, usage and cost: none yet.
- Expected cost basis: about US$0.005–0.01 per reading; five receipts should cost a few cents. This is an estimate to be measured.

7. RISKS / DECISIONS FOR CTO
Expected charges if approved:
- Render worker, Starter: about US$7/month, billed while running, for at most one month, then suspended.
- Anthropic: hard-capped by the US$5 workspace limit; expected spend a few cents.
- Possible minimum credit purchase: the founder reports it before buying if it exceeds US$5.
- No change to the free web service or database.
Approvals needed:
- the founder's explicit approval of the pilot budget;
- separately, before 2 November 2026, the in-place upgrade (about US$20.30/month baseline).
Remaining evidence for first-release acceptance:
- five live receipts R1–R5: accuracy and corrections, latency, attempts, tokens, actual cost;
- reading creates no cost; refusal with entries kept; a single confirmation accurate to the penny; idempotency;
- private originals protected; failure leaves manual entry available;
- key disabled and worker suspended at the end.
Risks:
- The Render dashboard may differ from the documented labels or prices; the founder stops and reports.
- A minimum Anthropic credit purchase above US$5 needs reporting.

8. FOUNDER REVIEW
- Read docs/receipt-pilot.md.
- If you approve the pilot budget, confirm the Render quote, then follow steps A–E in order.
- Feedback needed:
  - your approval;
  - the worker's start log lines and the receipt_jobs output (no secrets);
  - the R1–R5 notes and the Anthropic Console's actual spend.
