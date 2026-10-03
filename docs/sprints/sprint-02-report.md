ROOM BY ROOM — SPRINT 2 REPORT TO CHATGPT CTO
Date: 3 October 2026
Status: ready for review. Implementation complete; LIVE extraction accuracy UNVERIFIED (no API key or real receipt in this environment). First release NOT accepted.

1. OUTCOME
On the review page the owner can choose "Read receipt automatically". The page states what is sent and to whom.
A separate worker (process_receipts) sends the receipt image or PDF to the Anthropic Messages API using structured outputs.
The worker validates and normalises the result server-side and fills the draft only if the draft is still open and unchanged since reading was requested.
The page polls for status without replacing anything the owner has typed. The owner then checks flagged values, chooses projects and splits (the model never chooses them), acknowledges any duplicate or currency warnings, and confirms exactly once.
Processing, failed, ready, held (late), foreign-currency, unreconciled and duplicate states all exist and are tested. No job or reading ever creates cost.
NOT done:
- The real adapter has never called the live API. It is exercised only with a mocked SDK client.
- Every reading shown in screenshots is synthetic (fake test extractor, labelled "Synthetic test reading").
- No real-receipt accuracy has been measured.
- No physical-iPhone Safari keyboard, camera or real HEIC test has been done.

2. SCOPE
Delivered (by CTO item):
1. Real Anthropic adapter (apps/receipts/extraction.py) behind ReceiptExtractor:
   - Official SDK anthropic==1.11.0 (pinned), messages.create with output_config.format json_schema.
   - Model from RECEIPT_MODEL; recommended claude-haiku-4-5.
   - Images are EXIF-rotated, downscaled to 1568px long edge and sent as JPEG; HEIC is sent via its JPEG preview. PDFs are sent as a base64 document.
   - The key and model are server-side only.
   - Missing configuration shows "Automatic extraction not configured" and manual review keeps working.
   - The fake adapter is selected only with RECEIPT_EXTRACTOR=fake and is labelled synthetic in the UI and in the worker output.
2. Processing outside web requests: `manage.py process_receipts --once | --watch [--interval N] [--max-jobs N]`.
   - Claims use SELECT … FOR UPDATE SKIP LOCKED. Each claim stamps a fresh claim_token and a 180s lease, and commits before the provider call, so no lock is held during the network request.
   - Finishing re-locks the job and accepts the result only if the token still matches; late or expired attempts are ignored.
   - Expired leases are recovered; a lease that expires with no attempts left fails the job ("did not finish in time").
   - One active job per document (partial unique constraint); attempts are bounded by a check constraint.
   - SDK retries are disabled (max_retries=0). At most 2 worker attempts, and only for timeout, connection, 429 and 5xx/overloaded errors, after a 30s delay. There is no retry storm: a backoff test verifies no immediate re-claim.
   - Refusal, max_tokens, malformed output, auth, model and bad-request errors fail at once with sanitised messages.
3. Protecting drafts:
   - The job records the draft version at request time.
   - If the draft changed, the result is HELD and offered via "Replace my values with the reading", which is version-checked.
   - If the draft was confirmed, attached or discarded, the result is DISCARDED and never applied.
   - Polling (/receipts/<uuid>/reading.json) returns status only. The page auto-reloads only if the form is untouched; otherwise it shows "Reading finished" and keeps the typed values (browser-tested).
   - All Sprint 1A version, transaction and idempotency safeguards are unchanged.
4. States:
   - Queued and processing (spinner, "Attempt n of 2"; a "worker may not be running" hint after 2 minutes; polling stops after 10 minutes).
   - Failed (sanitised reason, attempts used, tokens if any, "Try reading again", manual route).
   - Ready (model, input/output tokens, attempt, warnings, tax notes, "Items match the receipt total").
   - Held.
   - The provider explanation appears next to the action.
5. Normalisation (apps/receipts/normalise.py):
   - Decimal two-place amounts; junk, more than two decimals, or huge values are rejected and flagged.
   - Unknowns stay empty and are marked "Check". Lengths and rows are bounded (100 lines with a dropped-lines warning). Long digit runs are masked. Invalid or future dates are flagged.
   - Included tax is a note only, never added. Added tax becomes a labelled adjustment. Discounts are negative; delivery is a shipping line.
   - No balancing lines; a mismatch produces the warning "Items add up to £X but the receipt total is £Y. Add missing items or correct the amounts."
   - No items but a total: the owner can click to add one "Unitemised purchase" line.
   - Non-GBP: amounts are not prefilled; the receipt's figures are shown as hints. Unknown currency: prefilled but flagged.
   - Both currency cases require a server-validated "All amounts above are in pounds sterling (GBP)" confirmation before posting.
   - The system prompt treats receipt text as data and forbids choosing projects and outputting card or account numbers.
6. Duplicate warnings:
   - Kept: the checksum warning at upload.
   - Added at confirmation:
     - a purchase already evidenced by an identical file;
     - owner-scoped confirmed purchases with the same total, a date within ±3 days, and a similar or unknown merchant.
   - Confirmation is refused until every currently listed purchase is acknowledged; acknowledgement IDs are checked server-side and forged IDs don't count. Legitimate identical purchases are allowed after acknowledgement.
   - Attach-to-existing still adds zero cost.
7. Follow-ups: mismatch guidance now reads "Add missing items or correct the amounts" on the server and in the live Allocated bar. Delivery and discount are suggested only when evidenced on the receipt.
Deferred/incomplete, with reasons:
- Live-provider validation: no founder-authorised ANTHROPIC_API_KEY or real receipt was available.
- Physical-iPhone validation: no device is available to me.
Departures from CTO brief, with reasons:
- Duplicate acknowledgement is enforced on receipt confirmation only, not on manual purchase entry. Manual entry is a deliberate typed action; extending it is a one-line change if the CTO wants it.
- A late reading is "held", not merged field by field: the owner explicitly replaces their values or keeps them.
- No new dependencies beyond the anthropic SDK; no Celery or Redis.

3. CODE AND SETUP
Repository path, branch, commit(s), remote/PR only if actually created:
- /home/user/Room_by_room, branch sprint-2 (from the accepted 7aa643b), pushed to origin/sprint-2 with normal pushes.
- Commits: 6d1eacc (adapter, jobs, worker, normaliser, duplicates), a77d2d0 (polling browser tests, screenshots, docs), then this report. The final remote SHA is in the founder's message.
- No PR, no deployment, no paid service set up.
Exact install/migrate/seed/run/worker/test commands:
  pip install -r requirements.txt            (adds anthropic==1.11.0 → httpx2)
  python manage.py migrate                    (adds receipts 0002_extraction_jobs)
  python manage.py seed_demo --reset --password '<demo password>'   (demo account only)
  python manage.py runserver 0.0.0.0:8000
  python manage.py process_receipts --watch   (worker; separate process)   |   --once (cron/tests)
  pytest ; DATABASE_URL=postgres://... pytest ; pytest tests/browser -o addopts="" -p no:cacheprovider
  RECEIPT_EXTRACTOR=fake python scripts/screenshots_sprint2.py --password '<demo password>'
Environment variables required, without secret values:
- ANTHROPIC_API_KEY (server-side; empty → "not configured").
- RECEIPT_MODEL=claude-haiku-4-5.
- Optional: RECEIPT_EXTRACTOR=anthropic|fake, RECEIPT_TIMEOUT_SECONDS=60, RECEIPT_LEASE_SECONDS=180, RECEIPT_RETRY_DELAY_SECONDS=30.
- The existing Django variables are unchanged.

4. VALIDATION
Checks actually run and results (final code):
- SQLite: `pytest` → 192 passed, 8 skipped (the PostgreSQL-only concurrency tests).
- PostgreSQL 16: `DATABASE_URL=postgres://… pytest` → 200 passed.
- Browser (Chromium/Playwright, live server): `pytest tests/browser` → 9 passed. These are the 7 previous tests plus:
  - reading requested → polling → page reloads itself when untouched and shows the reading;
  - typing during reading → "Reading finished" shown and the typed merchant kept.
- New automated coverage:
  - normaliser (15): currency, tax, discounts, strict amounts, bounds, masking, injection-as-data, malformed shapes;
  - adapter with mocked SDK client (17): request shape, image downscaling, PDF and HEIC inputs, max_retries=0 and timeout, error mapping and sanitising, refusal/max_tokens/malformed handling with usage, configuration honesty;
  - job/workflow (18), including the full fake-adapter integration: request reading → worker → reviewed draft → owner allocations with a split → confirm twice → exactly one purchase. Totals: Office £23.72, Hallway £3.50, shared £3.95, overall £31.17;
  - duplicates (4);
  - PostgreSQL concurrency (3 new): competing claims (4 threads, 1 claim), concurrent read requests (1 job), job finish racing the owner's save (never overwrites).
- `manage.py check` clean; `makemigrations --check` clean.
- The test configuration forces ANTHROPIC_API_KEY empty, so no paid calls are possible. ANTHROPIC_API_KEY is also absent from this environment.
Screens inspected and viewport widths:
- I looked at: phone (390) processing, ready, fully reconciled, confirmed purchase, failed, foreign and Office costs; tablet (768) and desktop (1440) duplicate warnings.
- Every scenario was captured at 390, 768 and 1440. Screens I captured but did not look at individually: offer/queued at every width; 768 and 1440 ready, reconciled and failed; unreconciled at every width; costs at every width.
Actual screenshots and how the founder can open them: docs/screenshots/sprint2/ (38 PNGs), all at 390, 768 and 1440 unless noted:
- offer- (read button and provider explanation), queued-, processing- (attempt 1 of 2), ready-;
- reconciled- (Allocated £31.17 of £31.17 ✓ after allocating, with one split);
- duplicate-warning-768 and -1440 (similarity warning against the earlier width's purchase);
- confirmed-purchase-, office-costs-, costs-;
- failed- (2 of 2 attempts used), foreign- and foreign-confirm- (EUR, amounts not prefilled, GBP confirmation), unreconciled- (missing delivery flagged, no balancing line).
- ALL readings are SYNTHETIC: the fake extractor on the fictional sample receipt.
Results shown after the 390 confirmation:
- The confirmed purchase is £31.17: Wood glue £6.49, Brad nails £7.98, Sanding £8.50 split Office £5.00 / Hallway £3.50, Paint tray £4.25, Delivery £3.95 to Shared tools.
- Office net £139.32 (seed £115.60 + £23.72), budget left £1,060.68.
- Later widths confirmed the same synthetic purchase again after acknowledging the duplicate warning, so the totals in the 768 and 1440 shots include those deliberately acknowledged repeats.
Failed tests, untested behaviour and limitations:
- No failing tests.
- Untested:
  - the real Anthropic API (live request, real latency, real token cost, real accuracy);
  - physical iPhone Safari keyboard, camera capture and real HEIC files;
  - the --watch loop under a process supervisor (only --once and the loop code path are run in tests).
- SQLite has no row locks; worker concurrency guarantees hold only on PostgreSQL.

5. COST INTEGRITY
Purchase/allocation/refund/opening-balance examples verified:
- All Sprint 1/1A money tests still pass on both databases (the £76.50 / £9.50 refund / £20 shared fixture, opening balances, voids, corrections).
- New: readings, failed jobs, held and discarded results, and foreign drafts leave totals at £0.00 until confirmation (asserted in each job test).
Double submission, stale update and rollback results:
- Double-tap reading requests produce one job; three concurrent requests on PostgreSQL produce one job.
- Double confirm after a reading produces one purchase.
- A stale apply of a held reading is refused. A late job never changes a confirmed draft.
- An expired attempt's late result is ignored and the newer attempt's result applied.
- Finishing a job while the owner saves serialises: either the reading applies and the stale save is refused, or the save wins and the reading is held.

6. RECEIPT PROCESSING
Real adapter versus fake/test backend:
- The real AnthropicExtractor is implemented and tested only against a mocked SDK client.
- The FakeExtractor is used for integration tests and screenshots, and is labelled synthetic everywhere.
Provider/model, limits and observed usage/cost:
- Anthropic Messages API via anthropic 1.11.0; model claude-haiku-4-5 ($1 / $5 per million input/output tokens).
- Structured outputs are supported for claude-haiku-4-5-20251001, per https://platform.claude.com/docs/en/build-with-claude/structured-outputs.
- Vision: standard tier, 1568px long edge, 10 MB per base64 image (https://platform.claude.com/docs/en/build-with-claude/vision).
- PDF: 32 MB per request; 100 pages for models under 1M context (https://platform.claude.com/docs/en/build-with-claude/pdf-support).
- App bounds: 15 MB upload, 5 PDF pages, 100 lines, 8192 output tokens, 60s timeout, 180s lease, 2 attempts.
- Observed usage/cost: NONE — no live calls were made.
- Rough expectation, not measured: one 1568px image is about 1,600 input tokens, plus about 1,000 for the prompt and schema, plus a few hundred output tokens. That is roughly £0.003–£0.005 per reading on Haiku 4.5.
- Usage (input/output tokens, request id) is stored per attempt and shown on the review page.
Live sample tests actually performed, corrections required, failure paths:
- Live tests: none.
- Failure paths tested with mock or fake:
  - missing credentials (no job created; manual route works);
  - configuration removed after queueing (job fails "not_configured");
  - timeout → retry → exhaustion (2 attempts, then failed);
  - retryable then success;
  - refusal, max_tokens, malformed JSON and a schema-violating shape caught by the normaliser;
  - an unexpected exception (sanitised as "internal");
  - unreadable or limited files (Sprint 1 upload tests);
  - missing total and currency, non-GBP, unreconciled.
Missing credentials or live validation explicitly outstanding:
- A founder-authorised ANTHROPIC_API_KEY (server-side), RECEIPT_MODEL=claude-haiku-4-5, and at least one real receipt photo (ideally an iPhone HEIC plus a PDF).
- Until a live run is done and reviewed, extraction accuracy is unverified and the first release is not accepted.

7. RISKS / DECISIONS FOR CTO
- Model choice: claude-haiku-4-5 for cost. If live accuracy on real UK till receipts is poor, switch RECEIPT_MODEL to claude-sonnet-5-5 (about 2× cost) with no code change. Decision requested after the first live samples.
- Whether duplicate acknowledgement should also apply to manual purchase entry (currently receipts only).
- Data handling: a reading sends the receipt image or PDF to Anthropic. The UI states this beside the button, and reading is opt-in per receipt. The founder should confirm this is acceptable for his receipts.

8. FOUNDER REVIEW
Short steps to try on phone; include expected results:
1. Authorise and set ANTHROPIC_API_KEY and RECEIPT_MODEL=claude-haiku-4-5 in .env, then run `python manage.py process_receipts --watch` alongside the server.
2. Add receipt → Take photo of a real receipt → "Read receipt automatically".
   - Expected: "Waiting…", then "Reading…", then the page fills itself with merchant, date, total and items. Unclear lines are marked "Check". "Read automatically", the model and token counts are shown.
3. Correct anything wrong, choose a project for each item (split one if useful), and check that Allocated shows a tick. Confirm.
   - Expected: one purchase, and the project's Spent rises by the allocated amount.
4. Photograph the same receipt again and read it.
   - Expected: a duplicate warning that offers to attach it instead (no new cost).
5. Type in the merchant field while a reading is running.
   - Expected: your typing is kept and "Reading finished" is offered.
Feedback needed:
- Extraction accuracy on your real receipts (which fields needed correction).
- How long reading took.
- Whether the Haiku cost/quality trade-off is acceptable.
- Safari keyboard and camera behaviour on your iPhone.

9. PROPOSED NEXT SPRINT
Sprint 2A (validation-only, small):
- Run live readings on 5–10 founder receipts (JPEG, HEIC, PDF) with authorised credentials.
- Record per-field corrections, latency and actual token cost.
- Tune the prompt or model only if the evidence calls for it.
- Founder phone walkthrough of the first-user scenario.
- Fix any defects found.
No new features.

Awaiting founder-relayed CTO review before the next sprint.
