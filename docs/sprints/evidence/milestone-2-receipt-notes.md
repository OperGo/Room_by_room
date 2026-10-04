# Milestone 2: founder-reported receipt notes (sanitised)

Founder-reported results; no receipts, photos, merchants or amounts.

## Pre-R1 checks (4 October 2026)
- Web service: ANTHROPIC_API_KEY set privately; deployed commit 9372c48; /healthz/ ok; "Read receipt automatically" shown.
- Anthropic `Room by Room` workspace: monthly spend limit US$5; auto-reload off.

## R1: itemised
- Request-to-result: 11 s.
- Merchant ✓; date not printed on the receipt; the draft left it **blank** (not invented) and the founder entered it: manual completion, not a transcription error; total ✓; items 3 of 3 correct.
- Corrections: none.
- Once-only checks done on R1:
  - nothing recorded before confirming ✓
  - wrong total refused, entries kept ✓
  - confirmed once, costs exact ✓
  - back + confirm again, not doubled ✓
  - signed out, original link → sign-in page ✓

## Spend observations (founder-reported, 4 October 2026)
- Anthropic `Room by Room` workspace: about US$0.01 consumed; US$4.99 remaining of the US$5.00 purchased.
- Render "current usage" shown as US$1.69. Breakdown by service (cron vs database) and the cron job's age still to be confirmed; not yet a cron-only figure.
