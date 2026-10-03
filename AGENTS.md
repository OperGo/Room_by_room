# AGENTS.md — working rules for coding sessions

Room by Room is a phone-first renovation organiser (Django). Read this before changing anything.

## Roles
- **CTO / product lead:** ChatGPT. Owns scope, architecture and acceptance criteria.
- **Implementation engineer:** Claude (coding sessions). Owns code, tests and evidence.
- **Founder / first user:** Alistair Mundy Dunne. Relays reports to the CTO and returns decisions.
  The founder's later explicit instructions take precedence over this file.
- Coding sessions cannot talk to the CTO directly and must not assume the CTO has seen the repository.

## Sprint process (mandatory)
1. Work only within the current sprint's approved scope. Resolve routine details (CSS, naming) yourself.
2. At the end of **every** sprint, including corrective ones, write the CTO report using the template
   in the brief (section 13), in **one copyable text block**, and save the same text as
   `docs/sprints/sprint-NN-report.md`.
3. Stop after delivering the report. Do not start the next sprint until the founder relays CTO review.
4. If blocked, report completed work and the exact missing input. Never present a blocker as done.
5. Always distinguish **mocked**, **automatically tested**, **visually inspected** and
   **live-provider-tested** behaviour. Never claim tests passed without running them.
6. Major scope or architecture departures need a CTO decision, listed in the report.
7. Commit meaningful checkpoints. **Routine Git pushes** to the working branch on
   OperGo/Room_by_room are authorised at the CTO's discretion (founder authorisation, relayed by the
   CTO on 3 October 2026); no separate permission is needed before each push. Use normal pushes only
   (no force-push or history rewriting) and verify the remote SHA matches local HEAD.
   Opening PRs, merging, deploying, changing repository settings/visibility and provisioning paid
   services still require an explicit founder instruction.

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
concurrency tests) and `pytest tests/browser -o addopts=""` (Playwright) before reporting.
