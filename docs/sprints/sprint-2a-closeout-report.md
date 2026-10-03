ROOM BY ROOM — SPRINT 2A CLOSEOUT REPORT TO CHATGPT CTO
Date: 3 October 2026
Status: ready for review. All four closeout items are done. Nothing was created on Render, nothing was deployed and no API money was spent. Two items await founder action: the official Render validator run, and first-release acceptance (a real receipt through to a confirmed cost, plus the founder's physical iPhone walkthrough).

1. OUTCOME
- Every receipt editor the server returns from a submission now starts "dirty". That covers:
  - validation errors and opening-balance choices;
  - missing GBP confirmation and duplicate warnings;
  - stale confirmation and save conflicts.
  A reading that finishes meanwhile never reloads the page, and Read/Try-again stay blocked until a successful save. A normal page load of stored values stays clean, and polling still reloads untouched pages.
- The watch worker processes one job per iteration and checks for shutdown before every claim. On SIGTERM it finishes the job in hand, claims nothing new and exits without sleeping. Rehearsed with real processes: with two queued jobs, job 1 finished, the worker exited 4.5 s after SIGTERM, and job 2 stayed queued.
- render.yaml is corrected to the approved configuration:
  - no ANTHROPIC_API_KEY;
  - auto-deploy off on both services;
  - 0.5c-512mb web and worker;
  - 0.1c-256mb PostgreSQL 16 with a 1 GB disk and storage autoscaling off;
  - private database networking.
  It is validated offline. Render's official validator could not run here (see section 4).
- docs/deployment-render.md now covers:
  - the US$20.30/month baseline on an assumed Hobby workspace;
  - the workspace-tier and quotation checks;
  - the 80% capacity rule;
  - Anthropic cost "not measured";
  - attaching resources to the existing project;
  - exact deployment steps;
  - a local PostgreSQL 16 restore rehearsal, which was actually run here.
- Mocked or synthetic only: all readings use the fake extractor.

2. SCOPE
Delivered:
1. Submitted editors are preserved on every redisplay.
   - `_review_context` sets `editor_submitted = editor.data is not None` (the editor was rebuilt from POST).
   - review.html renders `data-dirty-on-load` from that flag instead of `save_conflict` only. Every receipt_confirm and receipt_save redisplay goes through this one shared path.
   - Submitted fields and the deliberate version checks are unchanged.
2. Worker shutdown.
   - `--watch` calls `process_available(max_jobs=1)` per iteration and loops straight back to the stop-flag check after a job.
   - When idle it waits up to `--interval` in 0.2 s slices that check the flag, so it never sleeps once stopping.
   - `--once` / `--max-jobs` are unchanged. Crash containment and lease recovery in jobs.py are untouched.
3. render.yaml:
   - Removed ANTHROPIC_API_KEY. A header comment documents private entry into the `room-by-room-shared` group after creation; both services inherit it.
   - `autoDeployTrigger: "off"` on both services.
   - Plans: `0.5c-512mb` for web and worker, `0.1c-256mb` for the database.
   - Database: `postgresMajorVersion: "16"`, `diskSizeGB: 1`, `storageAutoscalingEnabled: false`, `ipAllowList: []` kept.
   - No `projects:` key, so no duplicate project can be created. The resources are moved into the existing "Room by Room" project after the sync (documented).
4. docs/deployment-render.md rewritten as described in section 1.
   - Added a read-only `python manage.py restore_fingerprint` command. Its JSON output covers file count and digest, size and checksum mismatches, missing references, per-owner and per-project totals, and row counts. It contains no names, merchants or file bytes.
   - Used it for the local export-restore rehearsal.
Deferred/incomplete, with reasons:
- Official Render Blueprint validation: it needs a Render login and workspace, and api.render.com is blocked here.
- Creating Render resources, deploying and live API calls: not authorised.
- First-release acceptance: needs a real receipt through to a confirmed cost and the founder's iPhone walkthrough.
- Hosted supervisor behaviour: pending deployment.
Departures from CTO brief, with reasons:
- I added PyYAML==6.0.3 to requirements.txt, used only by the offline Blueprint test. The single requirements file already carries the test tools.
- The project attachment is a documented dashboard "Move" after the sync, not a Blueprint `projects:` block, to guarantee no duplicate project. It needs a CTO acknowledgement.

3. CODE AND SETUP
Repository path, branch, commit(s), remote/PR only if actually created:
- /home/user/Room_by_room, branch sprint-2a, starting from the reviewed c7f84e0.
- Code commit 7f3221f, then this report commit. Pushed normally to origin/sprint-2a; the final remote SHA is verified against local HEAD and given in the handoff message.
- No PR, merge, deployment or Render/paid resources.
Changed files:
- apps/receipts/views.py, templates/receipts/review.html, static/js/app.js (comment);
- apps/receipts/management/commands/process_receipts.py;
- apps/core/management/commands/restore_fingerprint.py (new);
- render.yaml, requirements.txt (+PyYAML), docs/deployment-render.md, docs/receipt-processing.md;
- tests: tests/test_reading_jobs.py (+4), tests/test_render_blueprint.py (new, 4), tests/test_restore_fingerprint.py (new, 1), tests/browser/test_flows.py (+2);
- scripts/screenshots_sprint2a_closeout.py; docs/screenshots/sprint2a-closeout/ (7 PNGs); docs/sprints/evidence/ (2 files).
Exact commands:
  pip install -r requirements.txt
  pytest
  DATABASE_URL=postgres://postgres@%2Ftmp%2Fpg/roombyroom pytest
  pytest tests/browser -o addopts="" -p no:cacheprovider
  python manage.py process_receipts --watch --interval 3 | --once [--max-jobs N]
  python manage.py restore_fingerprint > before.json   (then the same against the restored DB; diff)
  render blueprints validate render.yaml               (founder machine, after render login / workspace set)
Validated configuration (render.yaml):
- Env group room-by-room-shared:
  - PYTHON_VERSION=3.13.14;
  - DJANGO_SECRET_KEY (generateValue);
  - DJANGO_DEBUG=0, DJANGO_HTTPS=1, DJANGO_SECURE_COOKIES=1;
  - PRIVATE_STORAGE_BACKEND=database;
  - STATIC_MANIFEST=1;
  - RECEIPT_EXTRACTOR=anthropic;
  - RECEIPT_MODEL=claude-haiku-4-5-20251001.
- Web room-by-room-web:
  - python, 0.5c-512mb, frankfurt, autoDeployTrigger off;
  - build: pip install + collectstatic; preDeploy: migrate;
  - start: gunicorn (2 workers, 120 s timeout); healthCheckPath /healthz/;
  - DATABASE_URL from room-by-room-db.
- Worker room-by-room-receipts:
  - python, 0.5c-512mb, frankfurt, autoDeployTrigger off;
  - start: process_receipts --watch --interval 3;
  - maxShutdownDelaySeconds 90;
  - DATABASE_URL from room-by-room-db.
- Database room-by-room-db: 0.1c-256mb, frankfurt, postgresMajorVersion "16", diskSizeGB 1, storageAutoscalingEnabled false, databaseName/user roombyroom, ipAllowList [].
Environment variable names (no values):
- Unchanged from Sprint 2A.
- ANTHROPIC_API_KEY is now entered only privately in the dashboard env group. It is not in the Blueprint, Git or this report.

4. VALIDATION
Checks actually run and results (final code 7f3221f):
- SQLite: `pytest` → 222 passed, 8 skipped (PostgreSQL-only tests).
- PostgreSQL 16.14: `DATABASE_URL=postgres://postgres@%2Ftmp%2Fpg/roombyroom pytest` → 230 passed.
- Browser (Chromium/Playwright, live server): `pytest tests/browser -o addopts="" -p no:cacheprovider` → 14 passed (12 previous + 2 new).
- New browser regressions:
  - Returned editor during a reading:
    1. Start a reading; the worker claims it ("Reading the receipt…").
    2. Confirm with a total of £99.00 against £9.99 of items. The server returns the editor with an error.
    3. The job finishes and the stored draft holds the synthetic reading.
    4. "Reading finished… kept" appears. A window marker proves the same document (no reload). Merchant, total, item, amount and project are all kept, and there are 0 purchases.
    5. Save draft → 409 conflict with values kept → "Save draft (keep my version)" → saved.
  - Returned editor blocks retry:
    1. A reading fails and the page is loaded by GET: clean, with no dirty marker.
    2. Submit an invalid confirmation, then press "Try reading again": "You have unsaved changes" is shown and no new job is created.
    3. Save draft, then Try again (with the replace confirmation): the job is queued.
  - Both tests fail against the old template condition (`save_conflict` only): the page reloaded, so "Reading finished… kept" never appeared. Both pass with the fix.
- Other returned-editor paths (server test): one test POSTs the confirm view through five paths. Each returns `data-dirty-on-load` and the typed values, and none creates a purchase. The paths are:
  - validation failure;
  - stale version (409);
  - missing GBP acknowledgement;
  - possible duplicate;
  - opening-balance overlap.
  The same test asserts that a GET of stored values has no dirty marker. Save-conflict coverage from Sprint 2A is retained. The existing untouched-page polling browser test still auto-reloads and shows the reading.
- Worker:
  - Unit tests:
    - SIGTERM raised inside job 1 of 2 → job 1 succeeded/applied, job 2 queued (attempts 0, no claim token), time.sleep never called, the next run processes job 2;
    - the watch loop calls process_available(max_jobs=1) per iteration;
    - an idle wait wakes within one 0.2 s slice when stopped.
  - Live rehearsal (real processes, PostgreSQL 16, fake extractor, 6 s simulated latency, two queued jobs): SIGTERM at +2 s → "Processed 1 job(s). Stopped.", exit 0, 4.5 s after SIGTERM. Job 1 succeeded/applied; job 2 queued with attempts 0.
  - SIGKILL/lease (re-run here, 12 s lease): SIGKILL mid-reading → job processing (attempt 1) → immediate restart processed 0 (lease held) → restart after expiry → succeeded on attempt 2 of 2, applied.
  - Evidence: docs/sprints/evidence/sprint-2a-closeout-worker-rehearsal.txt.
- Blueprint:
  - Offline: `pytest tests/test_render_blueprint.py` → 4 passed. It checks:
    - the approved values and the absence of a `projects:` key;
    - that no secret values are present and ANTHROPIC_API_KEY is absent;
    - plan and enum membership.
    The allowed enum values come from Render's API types in the official render-oss/cli source (commit e864786, 2 Oct 2026, built from the Go module proxy): service plan "0.5c-512mb", Postgres plan "0.1c-256mb", Postgres version "16", autoDeployTrigger "off". Field names and rules are confirmed against web-search extracts of render.com/docs/blueprint-spec.
  - Official: `render blueprints validate render.yaml` (Render CLI built from that source). This is server-side validation.
    - Without a workspace: "Error: no workspace specified and no default workspace set".
    - With `-w`: "Error: failed to create client: run `render login` to authenticate".
    - api.render.com is also blocked here (proxy 403).
    GAP: not validated by Render; the founder must run it before applying (deployment doc, step 2).
- Restore rehearsal (local PostgreSQL 16.14, no Render resources):
  1. Source DB with the demo data (fictional), using database storage.
  2. `restore_fingerprint` → before.json.
  3. `pg_dump -Fc --no-owner --no-acl` (205 KB) → `pg_restore --exit-on-error` into a new local DB (exit 0); `migrate --check` showed none pending.
  4. Fingerprint → after.json; `diff` → identical: 3 files, digest 074d248a…, 0 missing, 0 checksum mismatches, total £995.10, 3 confirmed purchases, all row counts.
  5. App check on the restored DB: the owner downloaded the receipt (SHA-256 matched the upload checksum) and the photo; another owner got 404; anonymous was redirected (302); the home page returned 200.
  Evidence: docs/sprints/evidence/sprint-2a-closeout-restore-fingerprint.json. A real Render export has not been restored (there is no infrastructure yet).
Screens inspected and viewport widths:
- Inspected: a1 and a2 at 390; b1 at 390; a3 at 1440.
- Captured, not individually inspected: a1/a2 at 1440, a3 at 390.
Actual screenshots: docs/screenshots/sprint2a-closeout/ (7 PNGs, synthetic readings, demo data). The script asserts there is no reload.
- a1-returned-editor-while-reading (390, 1440): validation error returned while "Reading the receipt…".
- a2-reading-finished-no-reload (390, 1440): "Reading finished. Your changes… kept"; error and typed values still present.
- a3-returned-values-kept (390, 1440): typed merchant, £99.00 total, "My own item" £9.99 and its project.
- b1-returned-editor-retry-blocked-390: failed reading + returned editor → "Try reading again" blocked with "You have unsaved changes".
Note: a1/a2 also show "This exact file was uploaded before". An earlier aborted script run had uploaded the same synthetic file. It is unrelated to the fix.
Failed tests, untested behaviour and limitations:
- No failures in the final runs. Mid-sprint, the two new watch-loop tests failed on PostgreSQL only: the command's close_old_connections() closed the test transaction's connection. The tests now stub that call; the production code keeps it.
- Not done:
  - live API;
  - the physical iPhone;
  - the hosted Render supervisor, health check, pre-deploy migration and real-export restore;
  - the official Blueprint validator.

5. COST INTEGRITY
- Money rules are unchanged; all cost tests pass on SQLite and PostgreSQL.
- No purchases exist before confirmation:
  - every returned-editor path asserts zero purchases for the draft;
  - both browser regressions assert 0 purchases and £0.00;
  - the worker rehearsals left the confirmed-purchase count at 3 (the seeded demo).
- Idempotent confirmation (a double POST makes one purchase and both redirect to the same place) and the stale-confirm 409 still pass.

6. RECEIPT PROCESSING
Real adapter versus fake/test backend: unchanged. AnthropicExtractor is tested only with a mocked SDK; the fake extractor is labelled synthetic. No live calls.
Provider/model and limits: anthropic==1.11.0; RECEIPT_MODEL=claude-haiku-4-5-20251001. Bounds unchanged.
Live samples, observed usage/cost (USD): none. The Anthropic monthly cost is "not measured".
Missing for live validation:
- a founder-authorised ANTHROPIC_API_KEY, entered privately in the Render env group;
- real receipts;
- the founder's iPhone walkthrough.

7. RISKS / DECISIONS FOR CTO
Proposed hosting budget:
- About US$20.30/month before tax: web $7, worker $7, Postgres 0.1c-256mb $6, 1 GB storage $0.30, on an assumed Hobby workspace ($0).
- Not included: tax, excess bandwidth/build minutes, and Anthropic calls.
- Verify the workspace tier and the dashboard quotation before creation, and do not change the workspace plan.
- Storage: check before 80% (0.8 GB). Growth (for example to 5 GB, about +$1.20/month) needs an approved cost change.
Proposed live-test budget:
- A cap of US$5 of Anthropic spend for the first live test (about 10–20 real receipts on Haiku 4.5).
- Set it as a spend limit in the Anthropic console by the founder.
- Report actual usage from the per-job token records. The expected cost is far below the cap, but it is unmeasured.
Decisions needed:
- Acknowledge the dashboard "Move" into the existing project, rather than a Blueprint `projects:` block.
- Acknowledge PyYAML as a test-only dependency.
- Approve the live-test budget.
Remaining access gaps:
- No Render login/workspace or api.render.com/render.com access from this environment, so the official validator and the price re-check must run on the founder's machine.
- No API key, real receipts or iPhone.
Exact deployment steps (after founder approval; full detail in docs/deployment-render.md):
1. Dashboard: confirm the workspace tier (do not change it) and that the existing "Room by Room" project is present.
2. `render login`; `render workspace set`; `render blueprints validate render.yaml`. Fix any findings.
3. Blueprints → New Blueprint Instance → this repo, branch sprint-2a, render.yaml. Check the resources, plans, PG16/1 GB/autoscaling off/Frankfurt and the ≈ $20.30 quotation, then apply.
4. Move the web, worker, database and env group into the existing "Room by Room" project's environment, and confirm there is still exactly one such project.
5. After the first deploy (migrations run pre-deploy), check that /healthz/ on the onrender.com address returns {"status":"ok"}.
6. Web Shell: `python manage.py create_owner alistair`.
7. iPhone: sign in, upload a receipt, enter it manually. Expected: "Automatic extraction not configured".
8. When authorised:
   1. Add ANTHROPIC_API_KEY privately to room-by-room-shared and redeploy both services.
   2. Read one real receipt, review, allocate and confirm.
   3. Record the evidence (tokens and outcome, no receipt content).
9. Dashboard export → local PostgreSQL 16 restore rehearsal with restore_fingerprint.

8. FOUNDER REVIEW
Short steps (local now, or after deployment):
1. Open a receipt and press "Read receipt automatically". While it reads, enter a merchant, an item at £9.99 and a total of £99.00, then press Confirm purchase.
   - Expected: an error saying the items don't add up, with your values kept.
   - When the reading finishes: "Reading finished. Your changes on this page have been kept", with no page reload and no values lost.
2. On that page, press "Try reading again" (on a failed reading) or Read.
   - Expected: "You have unsaved changes. Press Save draft first…"
3. Press Save draft, then "Save draft (keep my version)".
   - Expected: saved with your values, and nothing recorded as cost.
Feedback needed:
- Approve resource creation (≈ US$20.30/month) and the live-test API cap.
- Run the official Blueprint validation and apply it yourself (or grant access).
- Schedule the iPhone walkthrough with real receipts.
