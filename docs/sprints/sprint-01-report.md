ROOM BY ROOM — SPRINT 1 REPORT TO CHATGPT CTO
Date: 3 October 2026
Status: ready for review (visual fidelity against the approved mockups NOT yet checked — mockups were not attached)

1. OUTCOME
The founder can sign in (single owner account, no signup), create projects (including older/completed ones with past dates), add tasks with estimates/due dates/dependencies, complete tasks (blocked tasks need an override note), plan tasks for "this weekend", upload/caption/delete project photos and choose a cover, keep a shopping list grouped by project or retailer with a Bought section, record manual purchases with itemised lines, shipping/discount/rounding adjustments and amount splits across projects / Shared tools / Unallocated, record refunds, correct or void purchases with reasons and history, add estimated opening balances with the covered-period overlap decision, and see project and overall cost totals with filters. Receipts (photo, image, HEIC, PDF) can be uploaded, are stored privately, and open a draft review screen beside the original where the owner enters the details manually, then confirms (exactly one purchase), attaches to an existing purchase (no new cost), saves the draft or discards it.
Not done / mocked: automatic receipt extraction does not exist yet (Sprint 2). The UI says "Automatic extraction is not available yet (planned for Sprint 2)". No fake extraction is presented. Nothing is sent to any AI provider.

2. SCOPE
Delivered: everything listed in the brief's Sprint 1 scope: setup/auth/models, owner protections, project/task/photo workflows, dependencies, shopping list, manual purchases/allocations, opening balances, refunds/corrections/voids, cost views, Home/Project/Shopping screens, private receipt upload and draft review UI, seed command, docs (README, AGENTS.md, DESIGN.md, docs/architecture.md, docs/receipt-processing.md), tests and screenshots.
Deferred/incomplete, with reasons:
- Live extraction, job worker, UI polling, probable-duplicate (merchant/date/total) warnings: Sprint 2 per the brief. The interface (ReceiptExtractor / ReceiptExtractionResult) and ExtractionJob model already exist.
- Mockup fidelity: the four approved images were not available in this session, so I could not compare against them.
- Home-screen install: a basic web manifest and icon only. No offline mode, as the brief requires.
Departures from CTO brief, with reasons:
- No Django admin installed. This avoids an owner-scoping bypass; the owner account is created with `manage.py create_owner`.
- A cancelled prerequisite no longer blocks its dependent task, because a cancelled task can never become "done". Open prerequisites still block unless an override note is given.
- One discount rule added: within a single purchase, a discount cannot make any destination's share negative. This keeps refund caps and per-project totals meaningful.
- Leaving the purchase Total blank uses the sum of the lines. If a Total is entered, it must reconcile exactly.
- Receipt drafts can be confirmed in Sprint 1 using manually entered values, so the manual receipt-to-cost path works end to end before extraction exists.
- An added `core` app holds shared helpers and the ChangeEvent audit model.

3. CODE AND SETUP
Repository path, branch, commit(s), remote/PR only if actually created: /home/user/Room_by_room (clone of github.com/OperGo/Room_by_room). Branch `sprint-1`, commits listed by `git log` (initial checkpoint 16afe22 plus the docs/screenshots commit). I pushed the branch to origin because the cloud container is temporary and the work would otherwise be lost. No PR was opened and nothing was deployed. If you did not want a push, tell me and I will remove the remote branch.
Exact install/migrate/seed/run/worker/test commands:
  python3.13 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
  cp .env.example .env   (set DJANGO_DEBUG=1 locally; optionally DATABASE_URL=postgres://...)
  python manage.py migrate
  python manage.py create_owner alistair
  python manage.py seed_demo --password '<demo password>'     (optional demo account; idempotent; --reset to recreate)
  python manage.py runserver 0.0.0.0:8000
  Worker: none in Sprint 1.
  pytest ; DATABASE_URL=postgres://... pytest ; pytest tests/browser -o addopts="" -p no:cacheprovider
Environment variables required, without secret values: DJANGO_SECRET_KEY (required unless DJANGO_DEBUG=1), DJANGO_DEBUG, DJANGO_ALLOWED_HOSTS, DJANGO_CSRF_TRUSTED_ORIGINS, DJANGO_HTTPS, DJANGO_SECURE_COOKIES, DATABASE_URL (optional; SQLite when unset), PRIVATE_STORAGE_ROOT (optional). ANTHROPIC_API_KEY and RECEIPT_MODEL are reserved for Sprint 2 and unused now.

4. VALIDATION
Checks actually run and results; distinguish SQLite/PostgreSQL/browser:
- SQLite: `pytest` → 127 passed, 5 skipped. The 5 skipped are the PostgreSQL-only concurrency tests.
- PostgreSQL 16 (local cluster): `pytest` → 132 passed, including the 5 threaded concurrency tests.
- Browser: Playwright with Chromium on Django's live server, `pytest tests/browser` → 4 passed:
  - phone project/task flow, including checks that nav targets are at least 44px and there is no horizontal scroll;
  - phone receipt upload → review → confirm, with a double tap on Confirm;
  - desktop line-split allocation;
  - no horizontal scroll at 390px on 6 pages.
- `manage.py check` clean. `check --deploy` gives only the expected local-DEBUG warnings. X_FRAME_OPTIONS is SAMEORIGIN on purpose so the receipt PDF preview can be framed.
- Contrast for all text tokens is at least 4.5:1 (computed; listed in DESIGN.md).
Screens inspected and viewport widths: I looked at Home, Project (tasks), Shopping and Receipt review at 390px, and Home and Receipt review at 1440px. All 9 screens (home, projects, project, project-costs, shopping, costs, purchase, add-receipt, receipt-review) were captured at 390, 768 and 1440.
- Fixed after inspection: task title and metadata running together; a stray "·" separator; the receipt image filling the whole phone screen; a clipped Total placeholder.
Actual screenshots and how the founder can open them: docs/screenshots/*.png in the repository (e.g. docs/screenshots/home-390.png, project-390-full.png, receipt-review-1440.png). Regenerate with scripts/screenshots.py.
Failed tests, untested behaviour and limitations:
- No failing tests.
- No comparison against the approved mockups (not provided).
- No physical iPhone testing. Camera capture and HEIC were tested only through emulated browser upload and synthetic HEIC files, which is not equivalent to a real iPhone.
- 768px screens were captured but I did not review each one in detail.
- No accessibility audit tool was run beyond labels, focus styles, tap sizes and the contrast checks.
- SQLite has no row locks; concurrency guarantees hold only on PostgreSQL.
- Not deployed: no HTTPS, backups or object storage are configured.

5. COST INTEGRITY
Purchase/allocation/refund/opening-balance examples verified (automated tests):
- Brief fixture: £76.50 = MDF £32 Office + filler £9.50 Hallway + primer £35 Office. Office £67.00, Hallway £9.50, overall £76.50.
- A £9.50 filler refund returns Hallway to £0.00 and overall to £67.00.
- A £20 shared tool raises overall to £87.00; Office stays £67.00 and Hallway £0.00.
- Other money tests:
  - shipping, discount and rounding lines;
  - the unit price is only descriptive;
  - the unitemised line;
  - exact allocation sums;
  - splits including Unallocated;
  - per-destination and cumulative refund caps;
  - void excluded from totals but kept with its reason;
  - void blocked while refunds exist;
  - corrections need a reason and the current version, keep a before/after history, and cannot undercut recorded refunds;
  - budget remaining and over-budget with a zero budget or no budget;
  - archiving a project, cancelling a task or deleting a photo leaves costs unchanged;
  - GBP-only and other database constraints.
- Opening balances:
  - a purchase in the covered period is refused until a choice is made;
  - "additional" keeps the balance;
  - "replace" lowers it in the same transaction, never below zero or above the purchase's project amount;
  - voiding the purchase reverses the replacement;
  - editing an estimate cannot go below the amount already replaced.
- Seed data reconciles: Office £115.60, Hallway £9.50, Bathroom £850.00 (estimate), overall £995.10.
Double submission, stale update and rollback results:
- Repeating a submission key returns the same purchase (tested on SQLite and PostgreSQL).
- Two concurrent threads confirming one draft create one purchase (PostgreSQL).
- Concurrent duplicate submissions create one purchase (PostgreSQL).
- Concurrent opening-balance replacements: one succeeds and the balance never goes negative (PostgreSQL).
- Concurrent refunds respect the cap (PostgreSQL).
- Stale project, task, draft, purchase and opening-balance saves are refused with a message.
- An exception in the middle of posting leaves zero purchases, lines and allocations (tested on both databases).

6. RECEIPT PROCESSING
Real adapter versus fake/test backend: neither exists yet. Only the interface (ReceiptExtractor / ReceiptExtractionResult), a NotConfiguredExtractor and the ExtractionJob model are in place. No fake extraction is presented as working.
Provider/model, limits and observed usage/cost if available: none. App limits implemented now:
- 15 MB per upload;
- 50 megapixels per image;
- PDFs up to 5 pages, rejected if encrypted;
- 100 lines per purchase;
- file type checked by content signature, not extension;
- JPEG, PNG, HEIC/HEIF (decoded and converted to JPEG for preview) and PDF.
Live sample tests actually performed, corrections required, failure paths: no live tests. Upload failure paths are tested with synthetic files: wrong signature, unreadable image, oversized, decompression bomb, password-protected PDF and too many pages.
Missing credentials or live validation explicitly outstanding: live extraction (Sprint 2) needs a server-side ANTHROPIC_API_KEY, a confirmed RECEIPT_MODEL and a real receipt sample from the founder.

7. RISKS / DECISIONS FOR CTO
- Please confirm or override the departures in section 2: no admin, cancelled prerequisites not blocking, no negative destination within a purchase, blank Total defaulting to the line sum, manual confirmation of receipt drafts in Sprint 1.
- The approved mockups must be attached to the Sprint 2 session so the screens can be compared with them. I make no fidelity claim until then.
- Sprint 2 live validation needs the founder to supply an Anthropic API key (server-side, paid) and at least one real receipt.

8. FOUNDER REVIEW
Short steps to try on phone; include expected results:
1. Run the server (README), then `python manage.py create_owner <you>`. Sign in on your phone (same Wi-Fi: http://<computer-ip>:8000; add the IP to DJANGO_ALLOWED_HOSTS). Home shows "No active projects yet".
2. Projects → New: create "Office cabinetry" with a budget. Add your remaining jobs. In a task, open Dependencies and pick what it waits for. The blocked task shows "Waiting on …" and cannot be ticked without a note.
3. From the project, tap Add shopping item. Tick it on the Shopping tab. Expected: it moves to Bought and Costs still shows £0.00.
4. Add receipt → Take photo. Expected: a Draft review with the photo beside the form. Enter the items and allocate them to the project, split one line if useful, then Confirm. Expected: the purchase page opens, the project's Costs tab shows the right total, and confirming again does not double it.
5. Open the same project on a desktop browser. Expected: sidebar navigation, two-column project layout and the cost table.
6. Optional: `seed_demo` and sign in as demo to see the fictional example data.
Feedback needed: anything confusing in the purchase/split editor; whether "Ready to start" and "Ready this weekend" match how you plan; any differences you notice from the approved mockups.

9. PROPOSED NEXT SPRINT
Sprint 2 as briefed:
- Anthropic adapter behind the existing interface, after verifying the current SDK, model and PDF/image limits.
- process_receipts --once/--watch with transactional claims, lease recovery and bounded retries.
- Processing/failed/ready states with polling.
- Normalisation and reconciliation flags pre-filling the existing editor.
- Probable-duplicate warnings with acknowledgement.
- A fake adapter for tests.
- Mockup comparison and fixes once the images are attached.
- Any CTO feedback from this report.

Awaiting founder-relayed CTO review before the next sprint.
