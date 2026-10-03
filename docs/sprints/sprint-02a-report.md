ROOM BY ROOM — SPRINT 2A REPORT TO CHATGPT CTO
Date: 3 October 2026
Status: ready for review. All four corrections done; Render deployment prepared but NOT created or deployed. Live extraction accuracy and first-release acceptance remain PENDING (no API key or real receipts in this environment).

1. OUTCOME
- Owner edits made during or around a reading are no longer lost.
  - A stale Save returns a recoverable conflict (HTTP 409) that keeps every submitted value: header, lines, splits, flags.
  - The page then shows the current version, and the owner saves again deliberately with "Save draft (keep my version)".
  - Structural edits mark the page as changed and stop the auto-reload: adding or removing items or adjustments, adding or removing splits, and the unitemised button.
  - Read and Try-again are blocked while there are unsaved changes. "Show the stored reading" and "Replace my saved values" say explicitly that they replace values.
- Malformed provider output is contained. Wrong container or member types become a permanent "malformed" failure after 1 attempt, with usage retained, no draft change and no cost, and the same worker run goes on to the next job.
- Reconciliation now describes only the lines kept. Truncated readings, or readings with skipped rows, are marked incomplete and never reconciled.
- Render deployment is prepared:
  - private files can live in PostgreSQL, shared by the web service and the worker;
  - /healthz/, WhiteNoise and gunicorn are in place;
  - render.yaml has web, worker and Postgres;
  - plan, costs, backups and steps are in docs/deployment-render.md.
- I rehearsed the deployment locally in production-like mode, including worker SIGTERM and SIGKILL behaviour.
- Mocked or synthetic only: every reading uses the fake extractor or a mocked SDK. Nothing has been deployed.

2. SCOPE
Delivered:
1. Editor preservation (blocking item):
   - Reproduced: the old receipt_save redirected on StaleObjectError, discarding the posted values. The new test asserted 409 where the old code returned 302.
   - Fix: receipt_save re-renders the review with the posted editor (PurchaseEditor parses lines, allocations, flags and foreign hints), status 409, the refreshed version in the form, and a conflict banner. A missing or malformed version shows its specific reason.
   - Row lock and version checks are unchanged. Nothing is forced, and no version is advanced to overwrite.
   - When the owner keeps their version, extraction metadata is kept but marked edited_by_owner and reconciled=False. The panel says "…then edited by you" and no longer claims "Items match".
   - JS: markDirty() runs on input/change, on the add/remove item, add adjustment, split and remove-split buttons, and on programmatic fills.
   - A save conflict page loads already marked as changed (data-dirty-on-load).
   - Read and Try-again forms have data-requires-saved. With unsaved changes they show "You have unsaved changes. Press Save draft first…" and do not submit.
   - If the draft already has saved values, Read asks for confirmation that the reading will replace them.
   - When a reading finishes during edits, the spinner and progress text are replaced by "Reading finished. Your changes on this page have been kept…", and "show the stored reading instead (replaces your changes)" asks for confirmation.
   - Limitation: without JavaScript the Read form cannot detect unsaved typing, but no polling or auto-reload happens without JavaScript either.
2. Invalid results:
   - Reproduced the CTO findings with the real code: uncertain_fields=[{}] and warnings=1 both raised TypeError.
   - Fix: normalise() validates containers (items, adjustments, uncertain_fields, warnings must be lists; members of the last two must be strings; scalar fields must not be objects or arrays) and raises NormaliseError otherwise.
   - run_claimed_job turns any normalisation exception into a permanent "malformed" failure with usage kept. Only the exception type is logged, never raw content.
   - process_available contains any crash in a job, marks that job failed and continues to the next job.
3. Reconciliation:
   - Reproduced: a 3-line cap with six £1 lines and a £6 total kept £3 but reported reconciled=True.
   - Fix: candidates are built first, then at most RECEIPT_MAX_LINES are kept, and sums use only the kept lines.
   - Dropped or skipped rows set incomplete=True with a "This reading is incomplete…" warning and never reconciled=True, even if the kept lines happen to equal the total.
   - The original total and "Add missing items or correct the amounts" are kept. No balancing line is added.
4. Render preparation:
   - DatabaseStorage (core.StoredFile, migration core 0002) selected with PRIVATE_STORAGE_BACKEND=database; the local filesystem remains the default for development.
   - Public /healthz/ (database check, no data; exempt from the HTTPS redirect).
   - WhiteNoise with hashed static files (STATIC_MANIFEST=1); gunicorn 26.2.0; whitenoise 6.12.0.
   - RENDER_EXTERNAL_HOSTNAME is added to ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS.
   - render.yaml has a shared env group, web, worker (maxShutdownDelaySeconds 90) and Postgres basic-256mb, all in Frankfurt.
   - docs/deployment-render.md covers the plan.
   - RECEIPT_MODEL is pinned to claude-haiku-4-5-20251001, and the returned model is stored per job (existing behaviour).
Deferred/incomplete, with reasons:
- Creating Render resources and deploying: explicitly not authorised in this sprint.
- Live API readings and the founder's iPhone walkthrough: no credentials, receipts or device.
- Hosted supervisor behaviour: pending deployment.
Departures from CTO brief, with reasons:
- Read and Try-again require a successful save rather than carrying unsaved values into the read request. This was the brief's second permitted option; it is simpler and keeps "read replaces saved values" explicit.
- Storage uses PostgreSQL instead of object storage. A Render disk can't be shared between services; this needs no extra vendor and is covered by database backups. Object storage remains a later option behind the same interface.

3. CODE AND SETUP
Repository path, branch, commit(s), remote/PR only if actually created:
- /home/user/Room_by_room, branch sprint-2a cut from the reviewed ef55be8.
- Commits: 6b81aaa (conflict, dirty tracking, read guard, normaliser, worker containment), c507008 (Render preparation, owner-edited state, screenshots), then this report. Pushed normally to origin/sprint-2a; the final remote SHA is given by the founder.
- No PR, no merge, no deployment, no Render or paid resources created.
Exact commands:
  pip install -r requirements.txt   (adds gunicorn 26.2.0, whitenoise 6.12.0)
  python manage.py migrate          (adds core 0002_stored_files)
  pytest ; DATABASE_URL=postgres://... pytest ; pytest tests/browser -o addopts="" -p no:cacheprovider
  python manage.py process_receipts --watch | --once
  Production-like rehearsal: DJANGO_DEBUG=0 PRIVATE_STORAGE_BACKEND=database STATIC_MANIFEST=1 … python manage.py collectstatic && gunicorn config.wsgi:application --bind 127.0.0.1:8100 --workers 2 --timeout 120
  Render (when approved): see docs/deployment-render.md "Steps once approved".
Environment variable names (no values):
- DJANGO_SECRET_KEY, DJANGO_DEBUG, DJANGO_HTTPS, DJANGO_SECURE_COOKIES, DJANGO_ALLOWED_HOSTS, DJANGO_CSRF_TRUSTED_ORIGINS, DATABASE_URL, PRIVATE_STORAGE_BACKEND, PRIVATE_STORAGE_ROOT, STATIC_MANIFEST, PYTHON_VERSION, RENDER_EXTERNAL_HOSTNAME (set by Render).
- Receipt reading: ANTHROPIC_API_KEY (private), RECEIPT_MODEL=claude-haiku-4-5-20251001, RECEIPT_EXTRACTOR, RECEIPT_TIMEOUT_SECONDS, RECEIPT_LEASE_SECONDS, RECEIPT_RETRY_DELAY_SECONDS.
- RECEIPT_FAKE_DELAY_SECONDS is for rehearsals with the fake extractor only.

4. VALIDATION
Checks actually run and results (final code):
- SQLite: `pytest` → 213 passed, 8 skipped (the PostgreSQL-only tests).
- PostgreSQL 16: `DATABASE_URL=postgres://… pytest` → 221 passed.
- Browser (Chromium/Playwright, live server): `pytest tests/browser` → 12 passed. That is the 9 previous tests plus:
  - type during reading → reading finishes → Save draft → 409 conflict with values kept → "Save draft (keep my version)" → reload keeps the owner's merchant, item and project; no cost;
  - add an item, add an adjustment, remove an item, add a split and remove it during reading, without typing → reading finishes → no auto-reload; line count and the added Delivery line kept;
  - type before Read → Read stopped with the "unsaved changes" note and no job created → Save draft → Read (with the replace confirmation) → job queued.
- Mutation check: with the structural markDirty line removed, the structural-edit browser test fails; restored, it passes.
- New server tests:
  - 11 normaliser tests: malformed containers and members (including the exact CTO cases), truncation, coincidental truncation match, skipped rows, a complete receipt still reconciling;
  - 4 job tests: malformed uncertain_fields, malformed warnings and a malformed nested row in a two-job worker run, plus a crash-containment test;
  - 1 save-conflict test that checks every retained field and the deliberate retry;
  - 4 database-storage tests (also run on PostgreSQL);
  - 1 health-check test.
- Retained and passing: stale-confirm/idempotency, GBP acknowledgement, duplicates/attachment, owner isolation and all PostgreSQL race tests.
- Production-like local rehearsal (no paid calls): DEBUG off, collectstatic with the hashed manifest, gunicorn on :8100, database storage, PostgreSQL.
  - /healthz/ 200; anonymous / redirects to sign-in; static CSS 200.
  - Signed-in receipt review loaded the receipt image from database storage (naturalWidth 900).
  - A sign-out POST without a CSRF token was refused (403).
- Worker rehearsal with the fake extractor, 8s simulated latency and a 12s lease:
  - SIGTERM 3s into a reading: the job finished (applied), then "Stopped."
  - SIGKILL 3s into a reading: the job stayed processing (attempt 1). An immediately restarted worker left it alone while the lease was valid, then recovered it after expiry and finished on attempt 2 of 2 (applied).
Screens inspected and viewport widths:
- Inspected at 390: finished-with-changes, save conflict, reloaded owner values, incomplete reading and malformed failure.
- Inspected at 768: reloaded owner values. At 1440: read blocked until saved.
- Captured but not individually inspected: c1 structural edits (390); a1/a2/a3 at 768 and 1440; a4 at 1440; b1 at 390 and 768.
Actual screenshots: docs/screenshots/sprint2a/ (18 PNGs, all synthetic readings):
- a1-finished-with-changes, a2-save-conflict, a3-conflict-values-kept, a4-reloaded-owner-values, b1-read-blocked-until-saved: each at 390, 768 and 1440;
- c1-structural-edits-kept-390, d1-incomplete-reading-390, e1-malformed-output-failed-390.
Failed tests, untested behaviour and limitations:
- No failing tests in the final run. Mid-sprint, a Sprint 1A test failed (a malformed-version save showed the generic conflict text); I fixed it by showing the specific reason.
- Not done:
  - live API;
  - physical iPhone (Safari keyboard, camera, HEIC);
  - the hosted Render supervisor, health checks, pre-deploy migration and restore test;
  - the no-JavaScript unsaved-typing case (documented above).

5. COST INTEGRITY
- All money-rule tests pass unchanged on both databases.
- Every new reading, conflict and malformed path asserts £0.00 recorded cost and zero purchases.
- Save conflicts never advance the version to overwrite. The deliberate retry is version-checked under the row lock.
- Confirmation remains transactional and idempotent.

6. RECEIPT PROCESSING
Real adapter versus fake/test backend: unchanged. The real AnthropicExtractor is tested only with a mocked SDK client; the fake extractor is labelled synthetic. No live calls.
Provider/model and limits: anthropic==1.11.0; RECEIPT_MODEL=claude-haiku-4-5-20251001 (pinned per CTO; the returned model is recorded per job). Bounds are unchanged.
Live samples, observed usage/cost (USD): none.
Missing for live validation:
- a founder-authorised ANTHROPIC_API_KEY, set privately;
- 5–10 real receipts (JPEG, HEIC, PDF);
- the founder's iPhone walkthrough.
First-release acceptance remains pending.

7. RISKS / DECISIONS FOR CTO
- Approve the Render topology and spend:
  - web Starter $7 + worker Starter $7 + Postgres basic-256mb $6 + about $0.30 storage, on a Hobby workspace at $0: about US$20.30/month, plus Anthropic usage;
  - region Frankfurt;
  - private files in PostgreSQL.
- Pricing source: render.com is blocked by this environment's network policy. Prices and platform rules come from web-search extracts of official Render pages (pricing, compute plans, disks, Postgres backups, free tier, deploys) and Render's GitHub example repo. They must be re-checked on render.com/pricing before applying. The founder can allow render.com in the environment's network settings.
- Access: an authorised session needs Render access (dashboard or API key), or the founder applies the Blueprint himself.

8. FOUNDER REVIEW
Short steps (local or after deployment):
1. Open a receipt, press "Read receipt automatically", and immediately type a merchant and an item amount.
   - Expected: "Reading finished. Your changes on this page have been kept…"
2. Press Save draft.
   - Expected: "Not saved yet: this draft changed…", with your values still shown.
   - Press "Save draft (keep my version)" and reload. Expected: your values remain.
3. Type something, then press "Read receipt automatically".
   - Expected: "You have unsaved changes. Press Save draft first…" and nothing is sent.
Feedback needed:
- Approve the Render plan and cost.
- Grant Render access, or plan to apply the Blueprint yourself.
- Confirm the region.
- Decide on a custom domain.
- Authorise an Anthropic key and supply receipts for the live-validation run.

9. PROPOSED NEXT SPRINT
Sprint 2B (only once access and authorisation are given):
- Apply render.yaml in the "Room by Room" project.
- Create the owner account and run a restore test.
- Verify health checks and worker SIGTERM/restart behaviour on Render.
- Run 5–10 live readings, recording corrections, latency, returned model, tokens and USD cost.
- Demonstrate one real receipt end to end plus duplicate attachment.
- Founder iPhone walkthrough.
No new features.

Awaiting founder-relayed CTO review before deployment or any later sprint.
