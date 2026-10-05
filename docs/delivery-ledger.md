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
| 3 | Everyday founder use and friction fixes | 11 Oct | Not started |
| 4 | Retained-data and deployment readiness, including a recovery check | 14 Oct | Not started |
| 5 | Final validation and founder go-live | 16 Oct | Not started |

## Current production state

| Item | Evidence | Source |
|---|---|---|
| Web (free) and cron job both deployed at `380c190` (application code identical to `c85e964`) | observed | production (CTO-observed, 5 Oct) |
| Auto-Deploy **on** for both services | **CTO decided: Off on web and cron. Not yet applied** (the CTO's Render plugin lacks this update operation) | production (CTO-observed) |
| "mac temp" external database access rule still present | **CTO decided: remove only this temporary Mac rule. Not yet applied** (same limitation) | production (CTO-observed) |
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
1. **Auto-Deploy Off** on the web service and the cron job. Decided; **not yet applied**. Until it is applied,
   every push or merge to `sprint-2a` deploys both services, and must be verified as a release.
2. **Remove only the temporary "mac temp" database access rule.** Decided; **not yet applied**.

Both need a Render dashboard edit that the CTO's Render plugin cannot perform. That edit is the smallest
remaining access action: someone with dashboard access applies the two settings, and the CTO verifies them.

## Next actions

| Owner | Action |
|---|---|
| CTO | Review PR #1's revised head; have the two decided Render settings applied, then verify them |
| CTO | Collect `receipt_jobs` via the command swap; record the cron 24-hour cost projection |
| CTO + founder | Run the controlled auth-failure check (`docs/receipt-runtime-decision.md`): mandatory empty-queue proof, then always restore. The founder taps Read and reports the owner evidence |
| Founder | Provide R2–R5 samples (mixed documents allowed); check extracted values |
| Claude | Consolidated Milestone 2 report once the evidence is in; Milestone 3 preparation that needs no samples |

## Releases

| PR | Head SHA | CI | Merged | Deployed | Production verified |
|---|---|---|---|---|---|
| Operating framework + lean CI (this ledger) | see handoff | see handoff | no | not needed (docs/CI/tests only) | — |
