# Delivery ledger (current)

The single current record of milestones, acceptance evidence, blockers and next actions. Updated with the
work (see `AGENTS.md`). Evidence labels: **local**, **CI**, **production (CTO-observed)**, **founder-reported**.

**Target:** founder-only go-live **Friday 16 October 2026** with automatic receipt reading. Public signup,
subscriptions and commercial launch are deferred.

**Operating framework (5 October 2026):** ChatGPT (CTO) owns technical delivery: review, merge, deployment
and verification, with Render access. Claude implements and opens PRs into `sprint-2a`. The founder gives
business direction, samples and product feedback; founder approval is reserved for the categories in
`AGENTS.md`.

## Milestones

| # | Milestone | Due | State |
|---|---|---|---|
| 1 | Runtime and persistence decision | 5 Oct | **Accepted** (cron every minute, paid PG18, free web) |
| 2 | Five live receipts through accurate confirmed costs | 8 Oct | **In progress**: R1 done; R2–R5 and checks outstanding |
| 3 | Everyday founder use and friction fixes | 11 Oct | **Prepared** (`docs/milestone-3-plan.md`); starts after Milestone 2 |
| 4 | Retained-data and deployment readiness, including a recovery check | 14 Oct | Not started |
| 5 | Final validation and founder go-live | 16 Oct | Not started |

## Current production state

| Item | Evidence | Source |
|---|---|---|
| Web (free) and cron job both deployed at `380c190` (application code identical to `c85e964`) | observed | production (CTO-observed, 5 Oct) |
| Auto-Deploy **on** for both services | **Kept On by CTO decision**: reviewed merges into `sprint-2a` deploy both; the CTO verifies afterwards | production (CTO-observed) |
| "mac temp" database access rule | **Removed by the founder; external access verified closed** | founder action; production (CTO-verified, 5 Oct) |
| PostgreSQL 18 paid `0.1c-256mb`; cron `* * * * *` Starter; API key on both services | as applied | founder-reported (4 Oct) |
| Anthropic workspace: US$5 monthly limit, auto-reload off; US$5 bought, about US$0.01 used | | founder-reported (4 Oct) |
| Cron cost so far: US$0.01 (elapsed period not yet recorded) | 24-hour projection outstanding | founder-reported (4 Oct) |

## Milestone 2 evidence

| Check | State | Source |
|---|---|---|
| R1 itemised: 11 s; merchant, total, 3/3 items correct; date absent from receipt, left blank (manual completion) | done | founder-reported |
| Reading records no purchase; wrong total refused with entries kept; exact confirmed costs; no double count; signed-out original link → sign-in | done (on R1) | founder-reported |
| Extraction failure leaves manual entry available | **local proof done**; production run outstanding | local (`tests/test_auth_failure_override.py`, `evidence/milestone-2-auth-failure-rehearsal.txt`) |
| R2 delivery/discount, R3 two-project split, R4 imperfect photo, R5 typical/PDF | outstanding (no samples to hand) | — |
| `receipt_jobs` metadata (attempts, model, tokens, timings) | outstanding: CTO command swap | — |
| Cron cost 24-hour projection (suspend if above US$5/month) | outstanding | — |
| Actual API consumed vs purchased | US$0.01 of US$5 (to refresh at close) | founder-reported |

Details: `docs/sprints/evidence/milestone-2-receipt-notes.md`; procedures: `docs/receipt-runtime-decision.md`.

## CTO decisions (5 October 2026)
1. **Auto-Deploy stays On** for the web service and the cron job; this supersedes the earlier Off decision.
   Reviewed merges into `sprint-2a` deploy both services, and the CTO verifies them afterwards. **No direct
   pushes to `sprint-2a`.**
2. **"mac temp" database access rule: removed** by the founder; the CTO verified that external access is
   closed. No further founder Render action is needed.

## Next actions

| Owner | Action |
|---|---|
| CTO | Final review of PR #1's head; authorise the merge; verify both auto-deployments |
| CTO | Collect `receipt_jobs` via the command swap; record the cron 24-hour cost projection |
| CTO + founder | Run the controlled auth-failure check (`docs/receipt-runtime-decision.md`): mandatory empty-queue proof, then always restore. The founder taps Read and reports the owner evidence |
| Founder | Provide R2–R5 samples (mixed documents allowed); check extracted values |
| CTO | Review the sign-in and form-finish PR (assessment gaps 3 and 4); then the allocation-shortcut PR (gap 1) and the receipt-drafts PR (gap 5), as instructed on 5 October |
| Claude | Consolidated Milestone 2 report once the evidence is in; triage of the founder's Milestone 3 friction log |

## Product assessment (5 October 2026)

Local build of `6ceefd6` with fictional demo data, captured at 390/768/1440 px. Receipt states are from the
fake extractor or a local worker; the only live evidence is R1 (founder-reported). Missing approved scope:
none found. Top gaps, ranked:
1. Receipt allocation takes one choice per line; project context is lost (fix before launch).
2. Free-tier cold start: unmeasured; paid web would need founder approval.
3. Sign-in broken at 1024 px and wider (layout bug).
4. Form finish defects.
5. "Receipts to review" rows are indistinguishable.

Details: `docs/assessments/2026-10-05-product-assessment.md`.

## Releases

| PR | Head SHA | CI | Merged | Deployed | Production verified |
|---|---|---|---|---|---|
| #1 Operating framework + lean CI | `6934f50` | green (run 3: SQLite, PostgreSQL 18) | **yes, `2765733`** (merge commit, CTO-authorised, head-SHA guarded) | **web and cron live at `2765733`** (CTO-verified) | cron: later runs succeeded (CTO-verified); **web health pending** (Render log query timed out) |
| #2 Milestone 3 plan + ledger update | `935e4d9` | green (SQLite, PostgreSQL 18) | **yes, `6ceefd6`** (merge commit, CTO-authorised, head-SHA guarded) | **web and cron at `6ceefd6`** (CTO-verified) | verified by the CTO |
| #3 Sign-in layout and form finish (gaps 3, 4) + assessment | see handoff | see handoff | no | will auto-deploy on merge (templates, CSS, form labels; no migrations) | — |
| #4 Assign unassigned items to a project (gap 1) | see handoff | see handoff | no | will auto-deploy on merge; **migration** `receipts.0003` (nullable FK + index) | — |
| #5 Distinguish receipt drafts on Costs (gap 5) | see handoff | see handoff | no | will auto-deploy on merge (view and template only; no migrations) | — |
