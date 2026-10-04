ROOM BY ROOM — SPRINT 2B (FREE PREVIEW PREPARATION) REPORT TO CHATGPT CTO
Date: 4 October 2026
Status: ready for review. The free-preview configuration is prepared and was rehearsed locally end to end. The founder now applies the checklist and runs the manual deploy; hosted behaviour is unverified until then. I have no Render access, so the existing resources' identifiers, regions, version and expiry are founder-supplied fields (listed below). Nothing paid was changed, and no API money was spent.

1. OUTCOME
- docs/deployment-render-free-preview.md gives the founder one exact dashboard checklist for the existing free web service:
  - branch sprint-2a, auto-deploy off, the CTO's exact build and start commands, /healthz/;
  - the ten environment variables, with DJANGO_SECRET_KEY and DATABASE_URL entered privately;
  - ANTHROPIC_API_KEY left unset.
  It also covers:
  - owner creation without Render Shell;
  - same-region and PostgreSQL-version checks;
  - free-plan limits;
  - manual pg_dump/restore;
  - a short iPhone walkthrough.
- The supplied failed log is explained. Only sprint-2a contains Gunicorn, WhiteNoise and DatabaseStorage, and none of the other remote branches (sprint-1, sprint-2) do, so the failed build most likely used one of those.
- Rehearsed locally with fictional data and no paid calls: 21/21 walkthrough checks passed. The setup was:
  - a fresh Python 3.13.14 build using the exact build command;
  - the exact start command, with production settings and one Gunicorn worker;
  - PostgreSQL 18.6 with TLS-only external access;
  - database storage.
- Owner creation used the existing interactive create_owner over TLS (PGSSLMODE=require), with the password typed only at the prompts.
- Compatibility: the full suite passes on PostgreSQL 16.14, 17.11 and 18.6. A new free database most likely runs 18.
- One pre-existing phone defect was found and fixed (CSS only): on iPhone-density screens, the two-column date fields made the new-project form scroll sideways and blocked a tap.

2. SCOPE
Delivered:
1. Preview configuration (docs/deployment-render-free-preview.md, section "Founder checklist").
   - Free services have no pre-deploy facility, so migrations run in the start command before Gunicorn (single instance, so no race).
   - Manually created services don't inherit the Blueprint env group; this is stated.
   - The deployable commit was checked: gunicorn 26.2.0, whitenoise 6.12.0, DatabaseStorage, and config.wsgi.application.
2. Account setup without Shell.
   - create_owner runs from the founder's machine, against the External URL, with PGSSLMODE=require. The URL parser ignores ?sslmode=, which a test now documents.
   - The URL is entered with `read -rs`, so it is hidden and not stored in shell history.
   - DJANGO_ALLOW_INSECURE_KEY=1 only lets the command start; PBKDF2 password hashes don't use SECRET_KEY (verified).
   - Access is limited to the founder's /32 IP during the session and closed afterwards.
   - No passwords appear in Git, reports or arguments. There is no signup or startup reset logic.
3. Existing resources.
   - The dashboard fields to supply are listed in the guide.
   - Same region: use the Internal URL. Different regions: use the External URL plus PGSSLMODE=require, without replacing anything.
   - Versions 16, 17 and 18 are verified locally; for anything else, stop and report.
   - deployment-render.md now acknowledges the preview, keeps the paid plan separate, and requires existing resources to be accounted for before any Blueprint application (upgrade in place versus migrate, plus Blueprint PG "16" versus a probable 18). That needs a CTO decision.
4. Honest and recoverable.
   - There is no worker, key, background thread or fake extractor, and the missing-key manual route is verified.
   - The guide documents spin-down after 15 minutes (about 1 minute to wake), and the 30-day expiry followed by a 14-day upgrade-only grace period and then deletion.
   - Free Postgres has no managed backups, so the guide gives a manual pg_dump/restore procedure checked with restore_fingerprint. pg_dump must match or exceed the server's major version.
   - Receipts and photos are stored in the database (PRIVATE_STORAGE_BACKEND=database).
Deferred/incomplete, with reasons:
- Applying the settings and the hosted deploy: the founder does this, per the CTO.
- Recording the real resource IDs, regions, version and expiry: there is no Render access here.
- Official Blueprint validation, paid hosting and the API budget: not approved, and unchanged.
Departures from CTO brief, with reasons:
- I fixed a pre-existing phone layout defect in static/css/app.css (`.field-row` columns now `minmax(0, 1fr)`, and date inputs `min-width: 0`). It blocked "create a project" on high-density phones, which the walkthrough needs. The phone-layout browser test now uses an iPhone-like DPR 3 and compares against the device width; the old helper could not see this overflow. It reproduced as failing before the fix and passes after.
- Not fixed (cosmetic, pre-existing): the label "Room (optional) (optional)" on the project form. Noted for a later sprint.

3. CODE AND SETUP
Repository path, branch, commit(s), remote/PR only if actually created:
- /home/user/Room_by_room, branch sprint-2a.
- Commits:
  - cd5c3ea: CSS fix and layout test;
  - 823e25c: free-preview documentation, rehearsal script, consistency tests and evidence;
  - this report commit.
- Pushed normally to origin/sprint-2a; the remote SHA is verified against local HEAD in the handoff message.
- No PR, merge, deployment, Render change or paid resource.
- Application code at the branch head is identical to the rehearsed build cd5c3ea; later commits changed only docs, tests and scripts.
Exact founder-applied settings (existing free web service):
- Repository: OperGo/Room_by_room. Branch: sprint-2a. Deploy the branch head, which contains this report. Auto-Deploy: Off.
- Build command:
  pip install -r requirements.txt && python manage.py collectstatic --noinput
- Start command:
  python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 1 --timeout 120
- Health check path: /healthz/
- Environment (set on the service itself):
  - PYTHON_VERSION=3.13.14;
  - DJANGO_SECRET_KEY: private, generated in Render;
  - DJANGO_DEBUG=0;
  - DATABASE_URL: the existing database's Internal URL, private;
  - PRIVATE_STORAGE_BACKEND=database; STATIC_MANIFEST=1;
  - DJANGO_HTTPS=1; DJANGO_SECURE_COOKIES=1;
  - RECEIPT_EXTRACTOR=anthropic; RECEIPT_MODEL=claude-haiku-4-5-20251001;
  - ANTHROPIC_API_KEY: unset.
  - Only if the service and database regions differ: the External URL plus PGSSLMODE=require.
- Owner (founder's machine, in the repo checkout and venv):
  read -rs DATABASE_URL; export DATABASE_URL PGSSLMODE=require DJANGO_DEBUG=0 DJANGO_ALLOW_INSECURE_KEY=1; python manage.py create_owner alistair; unset DATABASE_URL
  Open the founder's /32 inbound rule before running it and remove it afterwards.
Commands run here:
  pytest
  DATABASE_URL=postgres://postgres@%2Ftmp%2Fpg/roombyroom pytest                 (PostgreSQL 16.14)
  DATABASE_URL=postgres://postgres@%2Ftmp%2Fpg17:5434/roombyroom pytest          (17.11)
  DATABASE_URL=postgres://postgres@%2Ftmp%2Fpg18:5433/roombyroom pytest          (18.6)
  pytest tests/browser -o addopts="" -p no:cacheprovider
  PREVIEW_OWNER_PW=… PREVIEW_INTRUDER_PW=… python scripts/rehearse_free_preview.py   (passwords via env, generated per run)
Environment variable names (no values): as listed above, plus PGSSLMODE (owner setup, backups, and the different-region case) and DJANGO_ALLOW_INSECURE_KEY (local create_owner and restore_fingerprint only).

4. VALIDATION
Checks actually run and results (final code):
- SQLite: `pytest` → 226 passed, 8 skipped.
- PostgreSQL: 16.14 → 234 passed; 17.11 → 234 passed; 18.6 → 234 passed.
  - The server versions were confirmed through Django (pg_version 180006 and 170011).
  - PG 17 and 18 came from the postgresql-binaries wheels in a local scratch directory.
  - A first PG16 run errored because the local PG16 server had stopped (container restart). After restarting it: 234 passed.
- Browser (Chromium): 14 passed. The phone-layout test now runs at DPR 3, covers /projects/new/, and fails without the CSS fix.
- New tests (tests/test_free_preview_config.py, 4):
  - the checklist contains the exact commands, branch, auto-deploy, health path and env values, with ANTHROPIC_API_KEY unset and no credentials;
  - Gunicorn, WhiteNoise, DatabaseStorage and config.wsgi.application are present;
  - URL query parameters are not forwarded (hence PGSSLMODE);
  - a missing key leaves extraction unavailable with the manual message.
- Free-preview rehearsal (docs/sprints/evidence/sprint-2b-free-preview-rehearsal.txt):
  - Build: a fresh Python 3.13.14 venv ran the exact build command (exit 0; 17 static files post-processed).
  - Start: the exact start command applied 24 migrations, then ran one sync worker. The app's DB connection used TLSv1.3.
  - Owners: create_owner ran for "alistair" and "intruder" over the external-style URL with PGSSLMODE=require, through a pseudo-terminal. The passwords were typed at the prompts; output shows "[prompt answered]" and exit 0.
  - Negative check: PGSSLMODE=require against a server without TLS was refused ("server does not support SSL").
  - Walkthrough: 21/21 checks passed, through a local TLS proxy that adds X-Forwarded-Proto like Render's edge.
    - /healthz/ 200 over plain HTTP; HTTP→HTTPS 301; HSTS present.
    - Hashed CSS served by WhiteNoise with an immutable cache; session cookie Secure and HttpOnly.
    - The owner can open the private photo and receipt.
    - The missing-key message is shown and there is no Read button.
    - Reconciliation mismatch is flagged in the browser, and the server refused it with the entries kept. "Matches total" appears after correction.
    - The manual confirm posted £12.50. A replayed confirm POST returned the same purchase, and the costs page showed £12.50 total with the project at £12.50 of £500.
    - 17 pages showed no sideways scroll at 390 px, DPR 3.
    - Anonymous requests for the receipt and photo got 302 to sign-in; another account got 404 for the receipt, photo and purchase.
  - Database afterwards: 1 purchase, 1 confirmed; 3 private files in core_storedfile (25,889 bytes); 0 extraction jobs.
- Backup and restore (PG 18; docs/sprints/evidence/sprint-2b-backup-restore.txt):
  - pg_dump 16 refused the 18 server (version mismatch), which confirms the client rule.
  - pg_dump 18 -Fc over TLS (99,425 bytes) → pg_restore into an isolated local DB (exit 0).
  - restore_fingerprint diff: identical (3 files, 0 missing, 0 checksum mismatches, £12.50, 1 confirmed purchase).
Screens inspected and viewport widths:
- Inspected: p3 (receipt "not configured", 390) and p7 (new project at DPR 3, 390).
- Captured, not individually inspected: p1, p2, p4, p5, p6 (390).
Actual screenshots: docs/screenshots/sprint2b-preview/:
- p1-sign-in, p2-empty-owner-home, p3-receipt-not-configured, p4-reconcile-mismatch, p5-purchase-confirmed, p6-costs-once, p7-new-project-dpr3 (all 390).
Failed tests, untested behaviour and limitations:
- Final runs: no failures. Rehearsal-script issues found and fixed during the sprint (test code, not the app):
  - a URL wait that also matched /receipts/new/;
  - the photo redirect target;
  - the confirm-error URL;
  - a costs-page text check.
- Not verified:
  - Render's build and runtime;
  - the HTTPS edge and health check on Render;
  - spin-down and wake-up;
  - the founder's real database (its region, version and expiry);
  - real external-URL TLS and the founder's IP rules;
  - the physical iPhone;
  - live extraction.

5. COST INTEGRITY
- Money rules are unchanged; all cost tests pass on SQLite and PostgreSQL 16, 17 and 18.
- The rehearsal confirmed the following:
  - nothing was recorded until confirmation;
  - an unreconciled confirm was refused;
  - a replayed confirm returned the same purchase;
  - the totals counted the purchase once.
- No receipt reading ran (0 jobs).

6. RECEIPT PROCESSING
Real adapter versus fake/test backend: unchanged. The preview runs with RECEIPT_EXTRACTOR=anthropic and no key, so automatic reading is unavailable ("Automatic extraction not configured. Enter the details from the receipt."). There is no worker in the preview.
Provider/model and limits: anthropic==1.11.0; RECEIPT_MODEL=claude-haiku-4-5-20251001. Unchanged.
Live samples, observed usage/cost (USD): none; not measured.
Missing for live validation: an approved API budget and key, a worker (paid plan), real receipts, and the iPhone walkthrough.

7. RISKS / DECISIONS FOR CTO
- Data loss: the free database expires 30 days after creation and is deleted after a further 14 days. The founder must record the expiry date and run the manual backup weekly and before expiry. Preview data should be treated as disposable unless exported.
- Region mismatch: if confirmed, the External URL plus PGSSLMODE=require keeps the existing resources (rehearsed TLS path), with some added latency.
- Future paid move: the Blueprint would currently create resources next to the free ones, and it pins PG "16" while the free DB is probably 18. Decide between upgrading in place and migrating before any application (see deployment-render.md).
- I fixed a small pre-existing CSS defect outside the strict scope (reported under departures).
Genuine access gaps:
- No Render dashboard or API access. The following must be supplied by the founder:
  - service name/ID, instance type, region, and the current repo, branch, commands and auto-deploy setting;
  - database name/ID, region, PostgreSQL version, created and expiry dates, and inbound IP rules.
- No physical iPhone, real receipts or API key.

8. FOUNDER REVIEW
Short steps (after applying the checklist and pressing Manual Deploy):
1. https://<service>.onrender.com/healthz/ → {"status": "ok"}. Allow about a minute if it was asleep.
2. Run create_owner from your Mac (guide section "Creating the owner account"), then remove your IP rule.
3. iPhone: sign in, create a project with a budget, and add a photo.
4. Add receipt → expect "Automatic extraction not configured". Enter the details, try a wrong total first (expect "Nothing was recorded…" with your entries kept), correct it, and Confirm once.
5. Costs shows the receipt total once. "Open original" and the project photo both display. After signing out, a receipt link goes to sign-in.
Feedback needed:
- The dashboard fields listed in the guide's "Before you start".
- Build/runtime logs if the deploy fails.
- Anything slow or wrong on the phone.
- The database expiry date.
