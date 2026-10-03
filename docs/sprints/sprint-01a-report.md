ROOM BY ROOM — SPRINT 1A REPORT TO CHATGPT CTO
Date: 3 October 2026
Status: ready for review (local only; not pushed — see section 3 and 7)

1. OUTCOME
All seven required corrections are implemented and tested.
- Receipt confirmation now checks the draft version under the draft row lock, inside the posting transaction. A stale, missing or malformed version creates no purchase. The page explains the conflict, keeps the user's entries and refreshes the version. An already-confirmed draft still returns its existing purchase.
- Save, attach and discard enforce the draft version in the same way.
- Cancelled prerequisites now block readiness and completion until the dependency is removed or an override note is recorded.
- Cost wording, Home, Project, Shopping, Receipt review and the demo presentation are corrected as described in section 2.
Nothing was mocked; no extraction work or new features were added.

2. SCOPE
Delivered (by CTO item):
1. Stale confirmation:
   - post_purchase(…, draft_version) validates under select_for_update. The order is: return the existing purchase if one exists, then refuse a handled draft, then refuse a version mismatch.
   - parse_version() refuses missing, malformed or less-than-1 values.
   - The confirm view returns HTTP 409, keeps the entered values and puts the current version in the form.
   - save_draft, attach_to_purchase and discard_draft require a matching version. The attach and discard forms now submit it.
2. Language:
   - "Purchase total (£, GBP)" replaces the old total label. No payment wording remains in the editor.
   - Main-flow guidance is now only "Items must add up to the purchase total. Leave the total blank to use the items' total."
   - The tax note moved into the Description and notes disclosure. "Sprint 2" wording was removed from the UI.
   - When the total is blank, the Allocated bar shows the calculated total ("Purchase total £X, calculated from the items").
   - Server errors say "Items add up to … but the purchase total is …".
3. Home:
   - Room by Room wordmark with the round add button, the "Make room for progress" headline and supporting copy.
   - A featured photo card (the active project with the most recent task completion), compact secondary project rows and a ready-work section.
   - "Add a receipt" is prominent and sticky, and the genuine "receipts waiting for review" link is kept.
   - No cost figures or extra badges on Home.
4. Project:
   - Order: title, task count, progress, cover (shorter), compact sage Spent/Budget panel, Tasks/Costs/Photos tabs, Next steps.
   - The budget-utilisation bar, the explanatory paragraph and the room line were removed. A status badge shows only when the project is not active.
   - Ready jobs are listed before blocked ones. Blocked jobs stay visible ("After …"), and done jobs are in a "Completed (n)" disclosure.
5. Shopping:
   - Forest-green selected segment (By project / By shop), sage uppercase group headings with counts, and light divided rows with no card framing.
   - One add control (the sticky "Add an item"); the quick-add card was removed.
   - Metadata: quantity · task · retailer when grouped by project, and project when grouped by shop.
   - The collapsible Bought section, Shared items and the "Bought items do not record a cost automatically" note are kept.
6. Receipt review:
   - Phone: a compact header (title, draft badge and a one-line note that extraction is unavailable), with a thumbnail that opens the original beside Merchant / Date / Purchase total.
   - Item cards keep the description, amount and project in the main row. Type, category, quantity, unit price, split and remove sit behind an accessible "Type, quantity or split" disclosure. Split rows stack below 600px so project names are not cut off.
   - The Allocated summary has a tick, and "Retake photo" plus "Confirm purchase" form one sticky row.
   - On phones, while a field has focus the sticky row returns to normal flow and the bottom nav hides; scroll-padding keeps focused fields visible.
   - Tablet uses a 34%/66% split, and line-card controls stay two columns at every width. Desktop keeps the full evidence beside the editor.
   - Manual entry, save draft, attach to an existing purchase and discard are all kept.
7. Demo:
   - A compact "Demo · fictional data" tag.
   - The schematic illustration is replaced by sample photos cropped from the approved generated mockups (apps/core/seed_assets/), labelled "Sample image" and captioned as not a real home. Real accounts still start empty.
Deferred/incomplete, with reasons: none within Sprint 1A scope.
Departures from CTO brief, with reasons: none new. The approved decisions are implemented. A blank manual total is calculated from the items and shown before confirmation, in the Allocated bar.

3. CODE AND SETUP
Repository path, branch, commit(s), remote/PR only if actually created:
- Path and branch: /home/user/Room_by_room, branch sprint-1.
- Sprint 1A code commit: 8a1dc9b06658b16086410c74bd1cdd63698c7148. This report is committed on top of it; the founder's message gives the final SHA.
- Not pushed. Per your instruction I paused remote writes: the founder has not given explicit push permission in this session.
- origin/sprint-1 is at 06812b0 (the fidelity pass). That push happened after a3194cd and before your review arrived, on the same basis as the first push.
- No PR has been opened and nothing has been deployed.
Exact commands:
  python3.13 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
  python manage.py migrate        (no new migrations in 1A; `makemigrations --check` reports no changes)
  python manage.py seed_demo --reset --password '<demo password>'   (demo account only)
  pytest
  DATABASE_URL=postgres://postgres@%2Ftmp%2Fpg/roombyroom pytest
  pytest tests/browser -o addopts="" -p no:cacheprovider
  python scripts/screenshots.py --password '<demo password>'   (dev server running)
Environment variables required, without secret values: unchanged from Sprint 1. No credentials are used.

4. VALIDATION
Checks actually run and results (on 8a1dc9b):
- SQLite: `pytest` → 138 passed, 5 skipped (the PostgreSQL-only concurrency tests).
- PostgreSQL 16: `pytest` → 143 passed.
- Browser: Chromium via Playwright on Django's live server → 7 passed:
  - phone project/task flow;
  - phone receipt upload → confirm, including a double tap;
  - desktop split allocation;
  - no horizontal scroll at 390px;
  - new: 44px touch targets on Home, Project, Shopping and Receipt review at 390px, with all disclosures open;
  - new: focused fields (total, item amount, project select, merchant) are not covered by sticky actions, and the bottom nav hides while typing;
  - new: keyboard focus starts at the skip link and focused controls show a visible outline.
  - I checked by hand that the touch-target test measures real elements (11–22 controls per page). It found the Bought header at 40px, which I fixed.
- `manage.py check` clean; no migration changes.
Screens inspected and viewport widths:
- I looked at Home, Project, Shopping and Receipt review (empty, filled with a split, and the error state) at 390px, Receipt review at 768px, and Project and filled Receipt review at 1440px.
- I compared them with the approved mockups (docs/mockups/). Layout, order and styling follow the mockups, with natural scrolling. Deliberate differences are listed in DESIGN.md.
- Screens I captured but did not look at individually: 768px Home, Project and Shopping; 1440px Home and Shopping.
Actual screenshots and how the founder can open them: docs/screenshots/, 74 files.
- Every screen at 390, 768 and 1440px: <screen>-<width>.png is the first view, -scrolled.png is one screen further down, and -full.png is the whole page.
- Filled receipt review with the Office/Hallway split, a delivery line and the allocated summary: receipt-filled-<width>.png and receipt-filled-<width>-summary.png.
- Validation error (total £31.17 vs items £18.94, "Nothing was recorded"): receipt-error-<width>.png. The database still held only the 3 seeded purchases afterwards.
Failed tests, untested behaviour and limitations:
- No failing tests.
- Not tested on a physical iPhone. The on-screen keyboard was not exercised; behaviour while typing was checked only by emulated focus in Chromium. Safari keyboard and viewport behaviour, camera capture and real HEIC files remain untested.
- I did not look at every 768px screen individually.
- No automated accessibility audit tool was run beyond the checks above.
- Test results are mine; nothing was independently verified.

5. COST INTEGRITY
Purchase/allocation/refund/opening-balance examples verified: the £76.50 split, the £9.50 refund, the £20 shared tool, opening-balance overlap and replacement, voids and corrections all pass unchanged, on both SQLite and PostgreSQL.
Double submission, stale update and rollback results:
- Stale-draft regression:
  - Draft at version 1 is saved elsewhere, moving it to version 2.
  - Confirming with version 1 → HTTP 409. No purchase is created and the total stays £0.00. The user's typed merchant is kept, and the form carries version 2.
  - A deliberate confirm with version 2 posts exactly one purchase. Repeating it, or retrying with version 1, returns the same purchase.
- Missing, empty, non-numeric, zero, negative or decimal versions → 409, nothing recorded.
- Calling the service directly with version 2 against a draft at version 3 raises StaleObjectError with no purchase. After a successful confirm, a stale retry returns the existing purchase.
- Stale save, attach and discard are refused, the draft is unchanged and no evidence is created. A malformed version gets a "missing its version" message.
- The PostgreSQL concurrent double-confirm test now passes the draft version and still produces exactly one purchase.
- Rollback and owner-isolation tests are unchanged and passing.
Cancelled prerequisites: a cancelled prerequisite now blocks readiness and completion ("a (cancelled)").
- An override with a note records ChangeEvent.after["override_prerequisites"] and the reason.
- Removing the dependency makes the task ready.
- Changing dependencies later leaves completion status and the override note intact.

6. RECEIPT PROCESSING
Real adapter versus fake/test backend: unchanged. Neither exists, and the UI says "Automatic receipt reading is not available yet."
Provider/model, limits and observed usage/cost: none.
Live sample tests actually performed: none.
Missing credentials or live validation explicitly outstanding: live extraction is Sprint 2. It needs a server-side ANTHROPIC_API_KEY, a confirmed RECEIPT_MODEL and a real receipt.

7. RISKS / DECISIONS FOR CTO
- Push permission and repository visibility. GitHub reports OperGo/Room_by_room as public. Sprint 1A exists only in a temporary cloud container and will be lost if the container is reclaimed. The founder needs to decide whether to:
  (a) authorise pushing to sprint-1, with or without making the repository private first, or
  (b) receive the work some other way.
  The demo seed contains only fictional data and imagery cropped from the mockups; no real receipts or personal data are in the repository.

8. FOUNDER REVIEW
Short steps to try on phone; include expected results:
1. Receipt review: upload a receipt photo.
   - Expected: the thumbnail sits beside Merchant/Date/Purchase total, with the first item card visible without scrolling.
   - Tap the amount field. Expected: the Confirm row and bottom nav move out of the way.
2. Open the same draft in two tabs. Save the draft in one tab, then Confirm in the other.
   - Expected: "changed elsewhere…" with your entries kept and nothing recorded. Confirm again: one purchase.
3. Cancel a task that another task depends on.
   - Expected: the dependent task stays blocked and is not under "Ready". Remove the dependency and it becomes ready.
4. Shopping: switch between By project and By shop, and tick an item.
   - Expected: it moves to Bought, and Costs is unchanged.
Feedback needed: whether the compact receipt layout and the "Type, quantity or split" disclosure work for you on a real iPhone; and the push decision in section 7.

9. PROPOSED NEXT SPRINT
Sprint 2 as briefed, once Sprint 1A is accepted and push permission is settled:
- Anthropic adapter behind the existing interface (verify the SDK, model and limits first).
- process_receipts --once/--watch worker with transactional claims, lease recovery and bounded retries.
- Processing, failed and ready states with polling.
- Normalised extraction pre-filling the current editor.
- Duplicate warnings.
- A fake adapter for tests.

Awaiting founder-relayed CTO review before the next sprint.
