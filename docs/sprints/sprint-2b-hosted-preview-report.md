ROOM BY ROOM — SPRINT 2B HOSTED PREVIEW (DEPLOYMENT SUPPORT) REPORT TO CHATGPT CTO
Date: 4 October 2026
Status: the hosted free preview is live and the founder's physical iPhone walkthrough passed all six required checks. One hosted usability defect was found: there is no sign-out control on phones. It is reported for scoping and not fixed. During account setup I added one deployment-support helper command (change-password) at the founder's request; it involves no application change. All hosted results are founder-reported: this environment's network policy blocks onrender.com (proxy 403), so I could not check the public service independently. First-release acceptance still needs live extraction through to accurate confirmed costs.

1. OUTCOME
- Public service: https://room-by-room.onrender.com/ (free web service, existing "Room by Room" project).
- Regions: web service Frankfurt; database Frankfurt (same region). The service uses the database's Internal URL.
- Database: Render free PostgreSQL, major version 18, expires 2 November 2026. Per Render's free-tier policy it is deleted after a 14-day upgrade-only grace period.
- PostgreSQL 18 is within the locally verified range (the full suite passed on 16.14, 17.11 and 18.6), so no compatibility action is needed.
- Founder-reported checks:
  - /healthz/ returned {"status": "ok"};
  - owner account `alistair` was created with the helper from the founder's Mac;
  - the founder is signed in on the iPhone.
- iPhone walkthrough (founder-reported, all passed):
  1. Project created with a budget; photo added to the project.
  2. Receipt photo uploaded; "Automatic extraction not configured" shown (no key, no worker).
  3. Mismatched total refused ("Nothing was recorded…") with the entries kept.
  4. Corrected total confirmed once; counted once on Costs and on the project.
  5. The original receipt ("Open original") and the project photo are both visible to the owner.
  6. The copied receipt-file link opened in a Safari Private tab (no session) showed the sign-in page, not the file. The founder used a Private tab because of the defect below.
- Database access: Render's default inbound rule `0.0.0.0/0` was removed.
  - Order: the founder's temporary /32 was added first; 0.0.0.0/0 was deleted; the owner was created; the /32 was then deleted.
  - The inbound list is now empty (no external access). This is the same-region case, so no service ranges are needed.
  - The founder reports /healthz/ ok afterwards.

2. SCOPE
Delivered (deployment support only; no product sprint):
- Guided the founder through the dashboard checks, the Mac checkout of sprint-2a (the founder's clone was on the default branch sprint-1 and was switched), the virtualenv, the temporary /32, create-owner, closing access and the walkthrough.
- change-password helper command (commit 99900c6):
  - The founder needed to reset the owner password. The app deliberately has no reset flow.
  - `python scripts/render_db.py change-password alistair` wraps Django's built-in `changepassword` with create-owner's protections: hidden URL prompt, 0600 PGPASSFILE, TLS required, settings scoped to the child, and clean-up on every exit path.
  - A short "Forgotten password" section was added to the guide.
  - The founder used it successfully on the hosted database.
Deferred/incomplete, with reasons:
- Phone sign-out defect: reported for CTO scoping, not fixed (no speculative application changes).
- First backup and restore check: not yet run (see section 7).
Departures from CTO brief, with reasons:
- I added the change-password command without prior CTO scoping. The founder was locked out and approved it in session. It is a helper-only change; the application files are unchanged.

3. CODE AND SETUP
Repository path, branch, commit(s), remote/PR only if actually created:
- /home/user/Room_by_room, branch sprint-2a.
- 99900c6: change-password command, its tests and the guide section. Then this report commit.
- Pushed normally; the remote SHA is verified against HEAD in the handoff message.
- `git diff cd5c3ea HEAD -- apps config templates static requirements.txt manage.py` is empty, so the deployed application code equals the accepted build.
- No PR, merge, paid change, API key or worker.
Hosted settings (founder-applied, as accepted):
- Branch sprint-2a; manual deploys; the accepted build and start commands; the ten environment settings.
- DATABASE_URL is the Internal URL; ANTHROPIC_API_KEY is unset.
Exact commands used by the founder (on the Mac, with the venv active):
  git fetch origin && git checkout sprint-2a && git pull
  python3.13 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
  python scripts/render_db.py create-owner alistair
  python scripts/render_db.py change-password alistair
Environment variable names: unchanged. No credentials are in chat, Git or this report.

4. VALIDATION
Checks actually run and results:
- Focused tests: `pytest tests/test_render_db_helper.py tests/test_free_preview_config.py` → 27 passed. The 3 new tests cover:
  - create-owner and change-password both run the management command with no password in arguments or environment, with TLS required and the passfile removed afterwards;
  - a failed change-password run cleans up and prints the connection hint.
- Real-process check against the local PostgreSQL 18.6 stand-in (fresh shell, TLS through the founder-IP relay, temporary /32 then removed):
  - change-password for `alistair` succeeded; the new password authenticates and the old one no longer does;
  - an unknown username is refused ("user 'nobody' does not exist");
  - no settings were left in the shell and no temporary passfile remained.
- Hosted, founder-reported: /healthz/ ok; owner created; password changed and signed in on the iPhone; walkthrough steps 1–6 passed.
- Independent hosted check: not possible from here (`curl https://room-by-room.onrender.com/healthz/` → "CONNECT tunnel failed, response 403" from this environment's proxy).
Screens inspected and viewport widths: none captured from the hosted service.
Actual screenshots: none.
Failed tests, untested behaviour and limitations:
- Hosted defect (reproducible by reading the code; founder-observed on the iPhone): there is no sign-out control below a 1024 px viewport.
  - The only Sign out button is in `.side-nav` (templates/base.html), which static/css/app.css hides with `.side-nav { display: none; }` except at desktop widths.
  - The phone's bottom navigation has no sign-out.
  - Repro: sign in on an iPhone and look for Sign out on any page; there is none.
  - Workaround: sign out from a desktop browser. Sessions otherwise persist on the phone.
  - Security note: private files remain protected (step 6).
- Not verified: spin-down and wake-up timing, and Render's own logs.

5. COST INTEGRITY
- Founder-reported on the hosted service: an unreconciled confirmation was refused; the corrected purchase was posted once and counted once on Costs and on the project.
- No live extraction and no API spend.

6. RECEIPT PROCESSING
- No key or worker; manual entry only, as approved.
- "Automatic extraction not configured" was shown on the hosted service.
- Live extraction remains unapproved and untested.

7. RISKS / DECISIONS FOR CTO
- Decision needed — phone sign-out defect. Proposed minimal fix for scoping: add a Sign out control reachable on phones (for example, a sign-out form at the foot of the Home page, or an account item in the bottom navigation), with a phone browser test. Needs CTO scope before I implement it.
- Data risk: the free database expires on 2 November 2026 and is deleted after the grace period. Recommended now:
  - the founder takes the first backup with `python scripts/render_db.py backup --out ~/RoomByRoomBackups` and runs restore-check. This needs PostgreSQL 18 client tools on the Mac (for example `brew install postgresql@18`);
  - then weekly, and before 2 November.
  The CTO should decide before expiry between upgrading in place and accepting the loss of preview data.
- Spin-down: the first request after 15 idle minutes takes about a minute (Render free tier). This is expected.
- Security notes:
  - A Django secret key was generated in this session at the founder's request and shown only in chat. Rotation is optional (it signs sessions out).
  - The founder's public IP appeared in chat; it was used only for the temporary rule, which has been removed.
Access gaps:
- No Render access, and onrender.com is blocked from this environment.
- No API key, receipt worker or approved live-extraction budget.

8. FOUNDER REVIEW
Done:
- the hosted preview is live at https://room-by-room.onrender.com/;
- owner sign-in works;
- walkthrough steps 1–6 passed.
Next, pending CTO decisions:
- take the first backup and restore check before relying on the data;
- review the phone sign-out fix once scoped.
