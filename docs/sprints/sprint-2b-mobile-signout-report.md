ROOM BY ROOM — SPRINT 2B PHONE SIGN-OUT CORRECTION REPORT TO CHATGPT CTO
Date: 4 October 2026
Status: the approved phone sign-out correction is implemented and tested locally. It is an application change, so it needs a founder-applied manual redeploy. Hosted behaviour is unverified until then. The incorrect desktop-browser workaround is removed from the persistent docs. The first backup and restore check has not been run yet; it is founder-run support, to follow.

1. OUTCOME
- Home now ends with an account row below 1024 px: "Signed in as <username>" and a clearly labelled "Sign out" button.
- The button is a POST form to the existing `accounts:logout` route with a CSRF token, uses the existing 44 px button style, and has the global visible :focus-visible outline.
- The row sits after the sticky "Add a receipt" button, so at the end of the page it rests below that button and above the fixed bottom navigation. The existing main padding keeps it clear.
- The row is hidden at ≥1024 px (`mobile-only`). The desktop sidebar Sign out and the four bottom-navigation destinations are unchanged.
- Sign-out still requires POST and CSRF: a GET returns 405 and a POST without a token returns 403, and the session survives both.
- Phone browser check: after Sign out, the session ends, and in the same browser context a private receipt-file URL goes to sign-in.

2. SCOPE
Delivered:
- templates/core/home.html: the account row.
- static/css/app.css: 3 rules (row layout, rule above it, long-name wrapping).
- Tests (see section 4).
- Screenshots.
- Corrected persistent guidance:
  - the Sprint 2B hosted-preview report now says the desktop workaround was invalid;
  - guide walkthrough step 8 now signs out on the phone itself (Home → bottom → Sign out) and re-opens the copied receipt link in the same browser.
Deferred/incomplete, with reasons:
- Hosted check of the new row: needs the founder's redeploy.
- First backup and restore check: founder-run on the Mac, not yet done.
Departures from CTO brief, with reasons: none. No new page, authentication mechanism, migration or unrelated polish (the laptop sign-in layout note is held for a later decision).

3. CODE AND SETUP
Repository path, branch, commit(s), remote/PR only if actually created:
- /home/user/Room_by_room, branch sprint-2a.
- 8f9af1d: phone sign-out, tests, screenshots, doc corrections; then this report commit.
- Pushed normally; the final remote SHA is verified against HEAD in the handoff message.
- No PR, merge or Render change by me.
Founder manual-deploy step (tied to the final SHA given in the handoff, which contains 8f9af1d):
1. Render → web service → Manual Deploy → deploy the latest commit of sprint-2a. Confirm that the deployed commit shown matches the handoff SHA.
2. Settings stay unchanged: the build and start commands, the ten environment variables, the Internal DATABASE_URL, no API key, no worker.
3. After the deploy:
   - /healthz/ → {"status": "ok"};
   - on the iPhone, Home → scroll to the bottom → "Signed in as alistair" with Sign out;
   - tap Sign out → sign-in page;
   - re-open a copied receipt "Open original" link in the same Safari tab group → sign-in page.
Exact commands (local verification):
  pytest tests/test_access.py tests/test_projects.py
  pytest tests/browser -o addopts="" -p no:cacheprovider
  python scripts/screenshots_sprint2b_signout.py --password <demo password>   (local demo data only)
Environment variable names: unchanged.

4. VALIDATION
Checks actually run and results:
- Focused tests:
  - `pytest tests/test_access.py tests/test_projects.py` → 60 passed.
  - With the helper/config tests: `pytest tests/test_access.py tests/test_free_preview_config.py tests/test_render_db_helper.py` → 69 passed.
  - The 2 new server tests:
    - Home contains the account row with the username, the POST form to /account/sign-out/, the CSRF token and the Sign out button, with two logout forms on the page (sidebar plus row);
    - with CSRF enforced, GET sign-out returns 405 and POST without a token returns 403, and the user is still signed in.
- Browser (Chromium/Playwright): `pytest tests/browser` → 17 passed (14 previous + 3 new).
  - Phone (390 px, DPR 3, touch):
    1. Sign in and confirm the owner can open a private receipt file.
    2. Open a project, tap Home in the bottom navigation, and find "Signed in as" and Sign out.
    3. The button is at least 44×44 px.
    4. elementFromPoint at its centre is the button itself, so neither the nav nor the sticky button covers it.
    5. It sits above the bottom navigation and does not overlap the sticky "Add a receipt" button.
    6. Tabbing reaches it, and its focus outline is not "none".
    7. There is no sideways scroll.
    8. Tap Sign out → sign-in page.
    9. The same context's request for the receipt-file URL → sign-in page; the root also redirects to sign-in.
  - Tablet (768 px): the row is visible and unobstructed, with no sideways scroll.
  - Desktop (1440 px): the row is hidden and the sidebar Sign out is visible.
  - Regression proof: with the previous Home template, the phone and tablet tests fail ("element(s) not found"). They pass with the change.
- Sanity check: `pytest` (SQLite) → 251 passed, 8 skipped. The PostgreSQL suite was not re-run: there was no data or query change, and the CTO asked for focused checks.
Screens inspected and viewport widths:
- Inspected: 390 (foot of Home), 768 (foot of Home), 1440 (desktop Home, row hidden, sidebar Sign out).
- Captured, not individually inspected: home-top at 390, 768 and 1440.
Actual screenshots (docs/screenshots/sprint2b-signout/, fictional demo data, local PostgreSQL 16):
- home-foot-sign-out-390, home-foot-sign-out-768: the row below "Add a receipt" and above the bottom navigation, with no overlap or overflow.
- home-desktop-sidebar-sign-out-1440: no Home row; sidebar "Signed in as demo" and Sign out.
- home-top-390, home-top-768, home-top-1440.
Failed tests, untested behaviour and limitations:
- No failures.
- Not verified: the hosted service (needs the redeploy) and the physical iPhone, including Safari's own rendering of the focus ring.
- The row exists only on Home by design (as approved); other pages reach it via the Home tab.

5. COST INTEGRITY
No change to money logic or data. Signing out does not affect drafts or recorded costs.

6. RECEIPT PROCESSING
Unchanged. No key or worker; manual entry only.

7. RISKS / DECISIONS FOR CTO
- The redeploy is needed before the founder can use the row. Free-tier spin-down applies, so the first load can be slow.
- First backup: still to do on the founder's Mac. It needs:
  - PostgreSQL 18 client tools, and a running local PostgreSQL 18 server for restore-check (installing the client alone does not start a server);
  - `--pg-bin` if the tools are not on PATH;
  - the temporary /32 only, with credentials at hidden prompts, and editing paused.
  Results will be reported as backup/restore outcome plus matching fingerprints only.
- The database expires on 2 November 2026. Weekly backups and the persistence decision are due before then.
- Held for a later decision (not changed): the sign-in page uses the phone-width card on laptops (cosmetic; the founder's observation).

8. FOUNDER REVIEW
1. Manual Deploy of sprint-2a's latest commit (section 3).
2. On the iPhone:
   - Home → bottom → Sign out → sign-in page;
   - a copied receipt link opened in the same browser → sign-in page.
3. Then the first backup and restore check on the Mac (separate founder instructions).
Feedback needed:
- the deployed commit;
- the iPhone sign-out result;
- the backup/restore result (fingerprints match: yes/no).
