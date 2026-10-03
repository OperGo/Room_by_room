# Architecture

## Shape
One Django project (`config/`) with five apps plus `core`. Server-rendered templates and ModelForms;
`static/js/app.js` adds line/split editing, reconciliation hints, upload auto-submit and
double-submit protection. Every action also works server-side.

## Ownership
- `AUTH_USER_MODEL = accounts.User`. `LoginRequiredMiddleware` protects every view except sign-in and the manifest.
- Every model has an owner directly (`Project`, `ShoppingItem`, `Purchase`, `ReceiptDocument`,
  `ReceiptDraft`, `ChangeEvent`) or via its parent. Views fetch with `owned(Model, user, uuid=...)`,
  which 404s for other owners. Destination keys posted from forms are resolved through the owner's
  projects only; services re-check ownership.
- No Django admin is installed, so there is no back door around owner scoping.

## Money model
- `Purchase(kind=purchase|refund, status=confirmed|void, total >= 0, currency='GBP')`
- `PurchaseLine(line_type, category, quantity > 0, unit_price (descriptive), amount signed)`
- `CostAllocation(destination=project|shared_tools|unallocated, project, amount)`
- `OpeningCostBalance(original_amount, amount remaining, coverage_through)` and
  `OpeningBalanceDecision(purchase, balance, additional|replace, amount_replaced, reversed_at)`
- `PurchaseEvidence(purchase, document)` — evidence never creates cost.

Database constraints: non-negative totals, GBP only, refund shape, void needs reason, positive
quantities, discounts negative, item lines non-negative, allocation/project consistency,
non-negative balances not above original, unique submission key per owner, one purchase per draft
(`Purchase.source_draft` one-to-one).

Service-level invariants (`apps/costs/services.py`, all in `transaction.atomic()` with
`select_for_update`): lines reconcile to total; allocations equal their line exactly; no destination
negative within a purchase; refunds capped per destination cumulatively; overlap with opening
balances requires an explicit decision; replacement reduces the balance in the same transaction and
is reversed on void/correction; corrections require a reason and current version and cannot undercut
recorded refunds; every change writes a `ChangeEvent` with before/after summaries.

Reporting (`apps/costs/selectors.py`): project net = opening balances + confirmed purchase
allocations − confirmed refund allocations. Overall = all of the above once, including shared and
unallocated. Drafts and extraction output are never queried.

## Concurrency and idempotency
- Stale forms: `version` fields checked under row lock → `StaleObjectError` → friendly message.
- Manual purchase/refund forms carry a `submission_key`; a duplicate submit returns the first record
  (unique constraint + `IntegrityError` recovery).
- Receipt confirmation locks the draft row inside the posting transaction. An already-confirmed draft
  returns its existing purchase (idempotent retries); otherwise the submitted draft version must match,
  and missing/malformed/stale versions are refused with nothing posted. Save, attach and discard check
  the draft version the same way.
- Verified by PostgreSQL threaded tests in `tests/test_concurrency_pg.py`. SQLite has no row locks.

## Files
`STORAGES['private']` → `PrivateFileSystemStorage` (no URL, 0600 files) under `PRIVATE_STORAGE_ROOT`.
Downloads only via owner-checked views with `nosniff`, `private`/`no-store` caching and explicit types.
Uploads are identified by signature, bounded in bytes and pixels; PDFs are checked for encryption and
page count. Project photos are re-encoded as upright JPEGs without EXIF/GPS. Receipt originals are kept
as uploaded; HEIC receipts also get a JPEG preview. A private object-storage backend can replace the
filesystem class later (with short-lived signed URLs issued only after the owner check).

## Tasks
`complete_task` blocks on any prerequisite that is not done — including cancelled ones (CTO decision,
Sprint 1A) — unless the dependency is removed or an override note is recorded. `set_dependencies` rejects self-links, cross-project links and cycles and
never alters completion history. "Ready" = open task in a planned/active project whose prerequisites are all done. Weekend selection stores the Saturday of the chosen weekend.
