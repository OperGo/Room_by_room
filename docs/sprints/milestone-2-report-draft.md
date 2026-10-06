ROOM BY ROOM — MILESTONE 2 REPORT (DRAFT STRUCTURE; to be completed when the evidence is in)
Status: draft. The bracketed items are outstanding. Known evidence is filled in with its source.

1. OUTCOME
Five live receipts through accurate confirmed costs:
| Sample | Type | Request→result | Values correct | Corrections | Confirmed cost exact | Source |
|---|---|---|---|---|---|---|
| R1 | itemised | 11 s | merchant, total, 3/3 items; date blank on the receipt (manual completion) | none | yes | founder-reported, 4 Oct |
| R2 | delivery/discount | [ ] | [ ] | [ ] | [ ] | founder-reported |
| R3 | two-project split | [ ] | [ ] | [ ] | [ ] | founder-reported |
| R4 | imperfect photo | [ ] | [ ] | [ ] | [ ] | founder-reported |
| R5 | typical / PDF | [ ] | [ ] | [ ] | [ ] | founder-reported |
Target: at least four useful drafts from legible samples.

Once-only checks:
1. Reading records no purchase: done on R1 (founder-reported).
2. Wrong total refused, entries kept: done on R1 (founder-reported).
3. Corrected confirmation exact: done on R1 (founder-reported).
4. No double count on repeat confirmation: done on R1 (founder-reported).
5. Signed-out original-file link goes to sign-in: done on R1 (founder-reported).
6. Extraction failure leaves manual entry available:
   - local proof done (tests/test_auth_failure_override.py; evidence/milestone-2-auth-failure-rehearsal.txt);
   - production run [ ]: CTO-run, with the founder's owner evidence.

2. RECEIPT_JOBS METADATA (sanitised; from the CTO's command swap)
[ jobs mapped to R1–R5, the failure check and the restoration read: attempts, model, tokens, timings, estimated cost ]

3. COSTS
- API: [ consumed ] of US$5.00 purchased; [ balance ]. Console, Room by Room workspace. (4 Oct: about US$0.01 consumed.)
- Cron: [ billed amount ] over [ known elapsed period ] → projected [ US$/30 days ] against the US$5/month threshold.
- Database: US$6.30/month (as approved).

4. RELEASES DURING MILESTONE 2 (all CTO-reviewed, head-SHA-guarded merges; auto-deployed; CTO-verified)
- #1 2765733: operating framework, CI.
- #2 6ceefd6: Milestone 3 plan.
- #3 b08919d: sign-in layout and form finish.
- #4 10c8b3a: allocation shortcut and worker migration guard (migration receipts.0003).
- #5 e99637a: receipt drafts list.

5. RISKS / DECISIONS FOR CTO
[ any accuracy defects; cold-start (K1) measurements; the recovery route decision ]

6. EVIDENCE SEPARATION
Local / CI / production (CTO-observed) / founder-reported, labelled per line above.
