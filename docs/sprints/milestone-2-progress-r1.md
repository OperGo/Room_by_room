ROOM BY ROOM — MILESTONE 2 PROGRESS (R1 COMPLETE, TESTING PAUSED) REPORT TO CHATGPT CTO
Date: 4 October 2026
Current milestone: 2 of 5 (due 8 October), in progress. 1 of 5 live receipts done; the founder has paused because no further receipts are to hand.
Status: pre-R1 checks confirmed; R1 passed with no corrections; all five once-only cost and privacy checks passed on R1. R2–R5, the intentional auth-failure test, receipt_jobs evidence, Console spend and the 24-hour cron check are outstanding.

1. OUTCOME
Pre-R1 confirmations (founder-reported):
- Web service: ANTHROPIC_API_KEY configured privately; deployed commit 9372c48; /healthz/ ok; "Read receipt automatically" shown.
- Anthropic `Room by Room` workspace: US$5 monthly spend limit; auto-reload off.
- Cron job (from setup): deployed at c85e964 with the key; first keyed run logged Claimable 0, Processed 0. 9372c48 differs from c85e964 only in documentation.
R1 (itemised), founder-checked against the paper:
- Request-to-result 11 s (target 1–2 min).
- Merchant ✓, total ✓, items 3 of 3 ✓. Date: not printed on the receipt, so not readable; how the draft handled it (left empty or guessed) is still to be confirmed by the founder.
- Corrections: none.
Once-only checks, all on R1:
1. Reading created no purchase (Costs unchanged before confirming) ✓
2. Wrong total refused, entries kept ✓
3. Corrected confirmation recorded exact costs ✓
4. Back + confirm again did not double-count ✓
5. After sign-out, the original-file link in the same browser went to sign-in ✓
6. Extraction failure leaves manual entry available: outstanding (planned as the intentional auth-failure test before R5).

2. SCOPE
Delivered: the pre-R1 checks, R1 and its evidence notes (docs/sprints/evidence/milestone-2-receipt-notes.md, sanitised: no merchants, amounts or images).
Deferred/incomplete, with reasons: R2 (delivery/discount), R3 (two-project split), R4 (imperfect photo), R5 (typical/PDF), the auth-failure test, receipt_jobs evidence, actual Console spend, the 24-hour cron usage check and the guide updates. The founder has no further receipts to hand today.
Departures from CTO brief, with reasons: none.

3. CODE AND SETUP
- Branch sprint-2a. 990a843: R1 evidence notes (documentation only); then this report commit (documentation only). No application change; no redeploy needed.
- Pushed normally; remote SHA verified against HEAD in the handoff message. No PR, merge or deploy.

4. VALIDATION
- Live-provider-tested (founder, hosted): R1 as above. One live reading.
- Not yet collected: tokens, attempts and timings from receipt_jobs; actual Console spend (expected about US$0.01 for one reading); cron billed usage.
- No automated suites rerun: no code changed since the accepted preflight.

5. COST INTEGRITY
Live evidence on R1 matches the tested behaviour: no cost from reading, refusal of a wrong total, exact single recording, idempotent re-confirmation.

6. RECEIPT PROCESSING
Haiku 4.5 (`claude-haiku-4-5-20251001`). 1 of 1 live reading useful with zero corrections. Accuracy across receipt types (delivery/discount, split, imperfect photo, PDF) is unproven until R2–R5.

7. RISKS / DECISIONS FOR CTO
Acceptance evidence so far: pre-R1 confirmations, R1 notes and five of six once-only checks.
Remaining launch blockers:
- Milestone 2: R2–R5, the auth-failure check, receipt_jobs evidence, Console spend, the 24-hour cron check, guide updates;
- Milestones 3–5 as planned (11, 14 and 16 October).
Estimated remaining effort: Milestone 2 about 1 h founder (once receipts are available) plus about 2 h Claude. Later milestones unchanged.
Effect on 16 October: on track if R2–R5 are done by 7 October; each day of delay after 8 October comes out of Milestone 3's everyday-use period.
Decisions requested:
A. While receipts are unavailable, may the founder run the intentional auth-failure test now, using a fresh disposable draft made from the R1 photo (a valid image, kept outside the five-sample count and left unconfirmed), and then restore the cron key? This takes about 15 minutes and needs no new receipt.
B. May Claude update the current guides now (approval, paid database, active cron) rather than with the final report?
C. Should the 24-hour cron usage check go ahead as planned independently of receipt testing? Recommended: yes.
D. If fewer than five suitable receipts are available by 7 October, is a mix acceptable (for example a supplier PDF invoice or an online order confirmation for R2/R5), or should Milestone 2's date move?

8. FOUNDER REVIEW
Relay this report; continue R2–R5 when receipts are available.
