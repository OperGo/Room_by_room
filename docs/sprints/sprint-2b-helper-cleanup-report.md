ROOM BY ROOM — SPRINT 2B HELPER CLEAN-UP REPORT TO CHATGPT CTO
Date: 4 October 2026
Status: ready for review. Both helper failure paths found by the CTO are fixed and covered by focused regression tests that fail on the previous helper. Application files are unchanged (still identical to the accepted build cd5c3ea). The web deployment does not need redeploying for this change. Hosted behaviour, owner creation on the founder's database and the iPhone walkthrough are still pending founder evidence.

1. OUTCOME
- RemoteDatabase.__enter__ now guards everything after the private temporary directory is created. If opening or writing the passfile raises or is interrupted, the directory and passfile are removed and the error is re-raised. The 0700 directory, the 0600 passfile, escaping and hidden input are unchanged.
- backup now protects the whole operation:
  - Before asking for the URL, it refuses if either today's dump name or its fingerprint name already exists, so earlier backups are never overwritten or deleted.
  - It tracks only the files this attempt creates. It removes them on any failure or interruption in pg_dump, the post-export fingerprint, the comparison, or creating or writing the fingerprint file.
  - Unrelated earlier backups in the same folder are untouched.
- No change to the build or start commands, the ten environment settings, database file storage, manual deploys, or "no API key or worker".

2. SCOPE
Delivered: the two bounded fixes in scripts/render_db.py, plus regression tests in tests/test_render_db_helper.py.
Deferred/incomplete, with reasons: hosted checks, owner creation and the iPhone walkthrough. The founder runs these; I have no Render access, and the cloud coding environment must not be given database access.
Departures from CTO brief, with reasons: none.

3. CODE AND SETUP
Repository path, branch, commit(s), remote/PR only if actually created:
- /home/user/Room_by_room, branch sprint-2a.
- 4475191: helper clean-up and tests; then this report commit.
- Pushed normally; the remote SHA is verified against HEAD in the handoff message.
- No PR, merge, deployment or Render change.
- `git diff cd5c3ea HEAD -- apps config templates static requirements.txt manage.py` is empty.
Exact commands:
  pytest tests/test_render_db_helper.py tests/test_free_preview_config.py
Environment variable names: unchanged.

4. VALIDATION
Checks actually run and results:
- Focused tests: `pytest tests/test_render_db_helper.py tests/test_free_preview_config.py` → 24 passed (13 new).
- The new tests cover:
  - Passfile initialisation failure (OSError and KeyboardInterrupt while opening/writing the passfile): the private directory is removed.
  - Backup failure paths, each leaving no output files and no temp directory:
    - post-export fingerprint error (connection lost) and interruption;
    - data changed between fingerprints;
    - pg_dump error and interruption after it created a partial file;
    - fingerprint-file write failure after the file was created.
  - Success: both files are created with mode 0600 and the temp directory is removed.
  - An existing dump name, an existing fingerprint name, or both: refused before any URL prompt or passfile is created, with the existing files' contents preserved.
  - An unrelated earlier backup pair in the same folder is untouched when a new attempt fails.
- Regression proof: the same tests run against the previous helper (55776f5) gave 7 failed and 12 passed. The failures were:
  - both passfile-initialisation cases;
  - post-export fingerprint error and interruption;
  - fingerprint-write failure;
  - the existing-fingerprint-name case;
  - the unrelated-backups case, where the old helper left the new dump behind.
  That run left two empty passfile directories in /tmp, which was the reported defect. I removed them, and the fixed run leaves none.
- Real-process smoke check (fresh shell, PostgreSQL 18.6 stand-in, TLS, founder-IP relay with a temporary /32):
  - `backup` wrote a 99,442-byte dump plus its fingerprint, both -rw-------, with no temp directory left.
  - A second same-day run stopped with "…dump already exists; move it or choose another --out" and kept the first backup intact.
  - The /32 was then removed.
- Per the CTO, I did not repeat the full application/database suites or the browser screenshots (application code unchanged).
Screens inspected and viewport widths: not applicable.
Actual screenshots: none.
Failed tests, untested behaviour and limitations:
- None failing.
- SIGKILL still cannot run clean-up (documented previously).
- A second backup on the same day needs another --out folder, or the earlier pair moved; the message says so.

5. COST INTEGRITY
No application change. Backups still compare fingerprints, which cover financial totals and file digests.

6. RECEIPT PROCESSING
Unchanged: no key or worker in the preview, manual entry only. No live calls.

7. RISKS / DECISIONS FOR CTO
Founder deployment support (in parallel):
- The founder reports the free preview deployed successfully. Pending:
  - /healthz/ and sign-in checks;
  - owner creation;
  - the iPhone walkthrough.
- Where the command runs: owner creation runs on the founder's own Mac (an existing trusted local setup), so the temporary /32 is the Mac's public IP. I explained that I can't create the account from this cloud session: it has no Render or database access, and providing it would put the database password in chat. The cloud environment is not given access.
- Steps given to the founder:
  1. Add the Mac's /32.
  2. Run `python scripts/render_db.py create-owner alistair`. The External URL goes only into the hidden prompt.
  3. Remove only that /32, keeping any service ranges.
  4. Recheck /healthz/.
- Requested metadata only: the public service URL, the service and database regions, the PostgreSQL major version and the expiry date. No database URLs or passwords in chat, reports or Git.
- One note: during deployment I generated a Django secret key in this session at the founder's explicit request. It was shown only in the chat, never written to files, Git or reports. The founder may rotate it with Render's Generate button at any time; that only signs sessions out.
Decisions: none new. Paid upgrades, a worker and live API spending remain unapproved.

8. FOUNDER REVIEW
Short steps:
1. https://<service>.onrender.com/healthz/ → {"status": "ok"}, and the root address shows the sign-in page.
2. Update your checkout (`git pull` on sprint-2a), then create the account from your Mac with the helper, as above.
3. iPhone walkthrough:
   - create a project with a photo;
   - upload a receipt;
   - a wrong total is refused;
   - the corrected receipt is confirmed and counted once;
   - the original receipt and the photo are visible;
   - after signing out, a receipt link goes to sign-in.
Feedback needed:
- the service URL;
- the service and database regions;
- the PostgreSQL major version and the expiry date;
- walkthrough results (anything slow or wrong).
