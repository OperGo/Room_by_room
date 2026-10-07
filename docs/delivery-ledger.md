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
| 2 | Five live receipts through accurate confirmed costs | **Sat 10 Oct** (rescheduled from 8 Oct by the CTO on 7 Oct) | **Incomplete**: R1 done (founder-reported). R2–R5, the production failure check, `receipt_jobs` metadata, API spend and the cron-cost projection are scheduled for the owner session on Saturday 10 October |
| 3 | Everyday founder use and friction fixes | 11–13 Oct | **In progress**: product fixes from the assessment (#3–#5 released). CTO plan of 7 Oct: Home project costs (#7) and receipt unsaved-changes warning (#8) merged, production verification pending (CTO); reading connection feedback (#9) in revision after CTO review. Founder use and the friction log start with the Saturday session; everyday-use observation continues through 11–13 October |
| 4 | Retained-data and deployment readiness, including a recovery check | 14 Oct | **Route A selected**; helper released (`e14a0e3`, verified); drill **held** until the CTO obtains and recommends the temporary-instance quote and the founder approves the new spending — incomplete |
| 5 | Final validation and founder go-live | 16 Oct | Not started |

## Current production state

| Item | Evidence | Source |
|---|---|---|
| Web (free) and cron job live at `e14a0e3` (PR #6); migration `receipts.0003` applied (PR #4) | verified | production (CTO-verified, 6 Oct) |
| `sprint-2a` at `30b7d44` (#7, #8 merged 7 Oct; no migrations); Auto-Deploy expected to deploy web and cron | **not yet verified** | pending CTO verification |
| Auto-Deploy **on** for both services | **Kept On by CTO decision**: reviewed merges into `sprint-2a` deploy both; the CTO verifies afterwards | production (CTO-observed) |
| "mac temp" database access rule | **Removed by the founder; external access verified closed** | founder action; production (CTO-verified, 5 Oct) |
| PostgreSQL 18 paid `0.1c-256mb`; cron `* * * * *` Starter; API key on both services | as applied | founder-reported (4 Oct) |
| Anthropic workspace: US$5 monthly limit, auto-reload off; US$5 bought, about US$0.01 used | | founder-reported (4 Oct) |
| Cron cost so far: US$0.01 (elapsed period not yet recorded) | projection over a known elapsed period outstanding (CTO, Render usage) | founder-reported (4 Oct) |

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
| Founder | Provide R2–R5 samples (mixed documents allowed); check extracted values |
| CTO | Obtain the exact temporary-instance quote and recommend it to the founder (drill **held** until then) |
| Founder | Approve or decline the recovery quote (new spending), as recommended by the CTO |
| CTO | Verify web, cron and health at `30b7d44` (#7, #8) |
| CTO + founder | Run the consolidated owner test session (`docs/owner-test-session.md`): R2–R5, failure check, metadata, spend, cron cost |
| Claude | Consolidated Milestone 2 report once the evidence is in (structure: `docs/sprints/milestone-2-report-draft.md`); triage of the founder's Milestone 3 friction log; prepare the chosen recovery check |

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
| #3 Sign-in layout and form finish (gaps 3, 4) + assessment | `060ac91` | green (SQLite, PostgreSQL 18) | **yes, `b08919d`** (merge commit, CTO-authorised, head-SHA guarded) | **web and cron live at `b08919d`** (CTO-verified) | **verified** (CTO): `/healthz/` HTTP 200 `{"status":"ok"}`; later scheduled cron runs succeeded |
| #4 Assign unassigned items to a project (gap 1) + worker migration guard | `c562102` | green (SQLite, PostgreSQL 18) | **yes, `10c8b3a`** (merge commit, CTO-authorised, head-SHA guarded) | **web and cron live at `10c8b3a`** (CTO-verified); web log `Applying receipts.0003_draft_context_project… OK` | **verified** (CTO): `/healthz/` HTTP 200 `{"status":"ok"}`; later cron runs processed normally and finished successfully |
| #5 Distinguish receipt drafts on Costs (gap 5) | `c2af6fd` | green (SQLite, PostgreSQL 18) | **yes, `e99637a`** (merge commit, CTO-authorised, head-SHA guarded) | **web and cron live at `e99637a`** (CTO-verified). The web's first deploy timed out after a successful build; the CTO retried the same commit successfully. Root cause not established. | **verified** (CTO): public `/healthz/` HTTP 200 `{"status":"ok"}`; scheduled cron runs succeeded |
| #6 Recovery helper `restore_fingerprint --database-url-env`; owner test session; ledger | `e58568d` | green (SQLite, PostgreSQL 18) | **yes, `e14a0e3`** (merge commit, CTO-authorised, head-SHA guarded) | **web and cron live at `e14a0e3`** (CTO-verified) | **verified** (CTO): public health `{"status":"ok"}`; the next scheduled cron run succeeded. Recovery drill **held** pending quote approval |
| #7 Home project financial visibility; ledger; Saturday checklist | `a6c7292` | green (SQLite, PostgreSQL 18) | **yes, `0a339c3`** (merge commit, CTO-authorised, head-SHA guarded) | Auto-Deploy; pending CTO verification | **pending** (CTO); founder check 11 not run |
| #8 Receipt-review unsaved-changes indicator and leave warning | `54f5e92` | green (SQLite, PostgreSQL 18) | **yes, `30b7d44`** (merge commit, CTO-authorised, head-SHA guarded) | Auto-Deploy; pending CTO verification | **pending** (CTO); founder check 12 not run |
