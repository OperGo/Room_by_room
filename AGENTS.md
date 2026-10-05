# AGENTS.md — working rules for coding sessions

Room by Room is a phone-first renovation organiser (Django). Read this before changing anything.

## Roles (operating framework, 5 October 2026)
- **CTO / technical delivery owner:** ChatGPT. Owns scope, architecture, acceptance criteria, technical
  decisions, PR review, merge authorisation, deployment and production verification. Has Render access
  (Sunday.Je workspace → Room by Room project).
- **Implementation engineer:** Claude (coding sessions). Owns code, tests, evidence and PRs.
- **Founder / first user:** Alistair Mundy Dunne. Provides business direction, genuine samples, checks of
  extracted values and product feedback. The founder is **not** the default coordinator, reviewer or
  release operator. The founder's later explicit instructions take precedence over this file.
- Coding sessions cannot talk to the CTO directly; handoffs are relayed. Do not assume the CTO has seen
  the repository.

## Decisions and question routing
- Within approved scope, make routine implementation and testing decisions yourself.
- Address architecture, scope interpretation, review and release questions to the **CTO** in the handoff.
  Continue independent work while a CTO decision is pending.
- Do **not** ask the founder to approve routine fixes, documentation, tests, PR creation, reviewed merges or
  deployments, and do not repeatedly ask whether to continue an already authorised milestone.
- **Founder approval is reserved for:** material product/UX changes; new or increased spending; public
  launch or external communications; significant changes to personal-information handling; destructive
  actions or meaningful risk to existing data. Route these **through the CTO with a recommendation**.
- If access is blocked, name the exact limitation and the smallest necessary founder action. Never request
  credentials in chat, and never give the cloud coding environment external database access.

## Release loop
1. Release branch: **`sprint-2a`**. The repository default is still `sprint-1`: never target it by
   accident, and do not change repository settings, visibility or the default branch.
2. Open **one bounded PR into `sprint-2a`** from a short-lived branch. Hand off its URL, **exact head SHA**,
   actual test results and migration implications.
3. The CTO reviews the actual changes. Merge only the **reviewed head**, under CTO authorisation; if the
   head changes after review, return it for re-review.
4. CI (`.github/workflows/ci.yml`) runs SQLite and disposable PostgreSQL 18 suites on standard runners with
   fictional data, no production credentials and no live API calls. Keep it green.
5. **Auto-Deploy is On** for web and cron (CTO decision): a reviewed merge into `sprint-2a` deploys both, and
   the CTO verifies the deployed commit on each. Merged does not mean verified. **No direct pushes to
   `sprint-2a`**; every change goes through a reviewed PR.
6. Normal pushes only (no force-push or history rewriting); verify the remote SHA matches local HEAD.

## Reporting
- Keep **one current delivery ledger**, `docs/delivery-ledger.md`: milestones, acceptance evidence,
  blockers and next actions. Update it with the work, not in separate administrative rounds.
- Reports contain completed work, outstanding CTO decisions and essential founder actions only, plus:
  PR URL and head SHA, tests actually run, migrations, merge SHA, deployed SHA and production verification.
- Report evidence separately: **local**, **CI**, **independently observed production** and
  **founder-reported**; distinguish mocked from live-provider-tested behaviour. Never claim tests passed
  without running them. Never present a blocker as done; report material blockers promptly.
- Milestone reports go in `docs/sprints/` as one copyable CTO-only block.

## Non-negotiables
- Money: `Decimal`, GBP only for posted records, two decimals, inclusive prices, no tax maths, no FX.
- Only confirmed purchases/refunds and opening balances count. Drafts/extraction JSON never do.
- Financial changes go through `apps/costs/services.py` (atomic, row-locked, versioned).
  No financial side effects in signals or GET requests. No hard delete of confirmed purchases.
- Every query is owner-scoped (`for_owner`, `owned()`); UUIDs are not access control.
- Receipts and photos live in private storage, served only by owner-checked views.
- No real receipts, personal photos, databases or credentials in Git. Tests never call paid APIs.

## Commands
See README.md. Run `pytest` (SQLite) and `DATABASE_URL=postgres://... pytest` (PostgreSQL, includes
concurrency tests) before opening a PR; CI repeats both. Run `pytest tests/browser -o addopts=""`
(Playwright) for any change to templates, CSS or JavaScript.
