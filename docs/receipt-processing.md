# Receipt processing

Receipt reading is optional and explicit. Uploading only stores the file privately; the owner then
chooses **Read receipt automatically**. Nothing from a reading counts as cost until the owner reviews,
allocates and confirms the purchase.

## Provider and model (verified 3 October 2026)

| Item | Choice | Source |
|---|---|---|
| SDK | `anthropic==1.11.0` (official Python SDK, pinned in requirements.txt) | PyPI; SDK `messages.create` accepts `output_config` |
| Model | `RECEIPT_MODEL=claude-haiku-4-5-20251001` (pinned snapshot for reproducible validation; the model returned by the API is stored on each job) | Cheapest current Claude model ($1 / $5 per million input / output tokens) |
| Structured output | `output_config.format = {type: "json_schema", schema: RECEIPT_SCHEMA}` | https://platform.claude.com/docs/en/build-with-claude/structured-outputs (lists `claude-haiku-4-5-20251001`) |
| Images | Base64 JPEG, downscaled to 1568 px long edge (standard vision tier), EXIF-rotated; HEIC sent via its JPEG preview | https://platform.claude.com/docs/en/build-with-claude/vision (10 MB per base64 image, 8000×8000 max, standard tier 1568 px) |
| PDFs | Base64 `document` block | https://platform.claude.com/docs/en/build-with-claude/pdf-support (32 MB per request; 100 pages when context < 1M) |
| Thinking / effort | Not sent (Haiku 4.5 does not take `effort`; transcription does not need thinking) | claude-api reference |
| SDK retries | `max_retries=0`; the worker owns the attempt budget | — |
| Timeout | `RECEIPT_TIMEOUT_SECONDS` (default 60 s read, 10 s connect) | — |

If accuracy on real receipts is poor, set `RECEIPT_MODEL=claude-sonnet-5-5` (about 2× the cost);
no code change is needed. Model and token usage are stored on every job.

## App limits

15 MB per upload; 50-megapixel decode limit; PDFs ≤ 5 pages and not encrypted; ≤ 100 lines kept per
reading (extra lines are dropped with a warning); 8192 output tokens per reading; text fields
truncated (merchant 120, descriptions 160 characters); long digit runs (card/account numbers) masked.

## Flow

1. Upload (photo, image, HEIC, PDF) → private storage → empty draft. Checksum duplicates warn.
2. **Read receipt automatically** (POST, with draft version) → one `ExtractionJob` (one active job per
   document; double taps return the same job). The page says what is sent and to whom.
3. Worker: `python manage.py process_receipts --watch` (or `--once` from cron/tests) claims jobs.
4. Result is normalised server-side and applied to the draft **only** if the draft is still open and at
   the version recorded at request time. Otherwise it is *held* (owner edited meanwhile; offered with
   "Replace my values with the reading") or *discarded* (draft already confirmed/attached/discarded).
5. The page polls `/receipts/<uuid>/reading.json` (status only). If the form is untouched it reloads to
   show the result; if the owner has typed, it shows "Reading finished" and never replaces their values.
6. Owner checks flagged values, chooses projects/splits (the model never chooses them) and confirms.
   Confirmation stays transactional, version-checked and idempotent (Sprint 1A).

## Worker

```bash
python manage.py process_receipts --watch            # long-running; Ctrl+C / SIGTERM to stop
python manage.py process_receipts --once             # process what is claimable, then exit
python manage.py process_receipts --once --max-jobs 1
```

- Claim: `SELECT … FOR UPDATE SKIP LOCKED` on the oldest claimable job, stamp a fresh `claim_token`,
  `attempts += 1`, lease `RECEIPT_LEASE_SECONDS` (180 s); **commit before calling the provider**.
- Finish: re-lock the job; accept the result only if the claim token still matches. An attempt whose
  lease expired and was re-claimed cannot overwrite the newer attempt.
- Retries: at most **2 attempts per job** (`RECEIPT_MAX_ATTEMPTS`). Only timeout, connection, 429 and
  5xx/overloaded errors are retried, after `RECEIPT_RETRY_DELAY_SECONDS` (30 s). Refusal, `max_tokens`,
  malformed output, auth/model/bad-request errors fail immediately. An expired lease with no attempts
  left fails the job ("did not finish in time"). Re-reading after failure is a new explicit user action.
- Usage (input/output tokens, request id, stop reason) is recorded per attempt and shown on the review.
- Without `ANTHROPIC_API_KEY` + `RECEIPT_MODEL` the UI says "Automatic extraction not configured"
  and offers manual entry; queued jobs fail with that reason.

## Normalisation rules (`apps/receipts/normalise.py`)

- Amounts are parsed to two-place `Decimal`; more than two decimals, huge or junk values become empty
  and flagged. Unknowns stay empty and are marked **Check**.
- GBP receipts: values prefilled. Unknown currency: prefilled but flagged and the owner must tick "All
  amounts above are in pounds sterling (GBP)". Non-GBP: amounts **not** prefilled; the receipt's
  figures are shown as hints; the same GBP confirmation is required. No exchange rates.
- Tax shown as included in prices is a note only (never added again). Tax added on top becomes a
  labelled adjustment line. Discounts become negative lines. Delivery becomes a shipping line.
- If items don't add up to the total: warning "Items add up to £X but the receipt total is £Y. Add
  missing items or correct the amounts." No balancing line is ever invented.
- No items but a total: the owner may click "Use one “Unitemised purchase” line for the total".
- The system prompt treats receipt text as data and forbids choosing projects or outputting card numbers.

## Malformed output (Sprint 2A)

- Wrong container or member types (e.g. `uncertain_fields: [{}]`, `warnings: 1`, a non-scalar merchant/total)
  are a schema failure: the job fails permanently as `malformed` after one attempt, usage is kept, the draft
  is untouched, nothing is logged from the receipt, and the worker moves on to the next job.
- Item/adjustment rows that are not objects are skipped; rows beyond 100 are dropped. Either makes the reading
  **incomplete**: it is never marked reconciled, and reconciliation is calculated only from the lines kept.
- Any unexpected exception in normalisation or finishing a job is contained at the job boundary.

## Editing while reading (Sprint 2A)

- Any change on the page (typing, adding/removing items or adjustments, splits, the unitemised button) marks
  it as having unsaved changes; polling then never reloads it.
- If a reading is stored while you edit, **Save draft** returns a conflict (HTTP 409) that keeps everything
  you entered and shows the current version; pressing **Save draft (keep my version)** saves it deliberately.
- "Read receipt automatically" and "Try reading again" are blocked while there are unsaved changes ("Save draft
  first"). If the draft already has saved values, the button warns that the reading will replace them.

## Duplicates

- Same file checksum: warning on upload; at confirmation, a purchase already evidenced by an identical
  file is listed as a possible duplicate.
- Same total, merchant similar (or unknown), date within ±3 days, confirmed purchase of the same owner:
  listed as a possible duplicate.
- Confirmation is refused until every listed purchase is acknowledged ("This is a separate purchase");
  the server checks the acknowledged IDs against the current list. Identical legitimate purchases are
  allowed after acknowledgement. Attaching to an existing purchase adds no cost.

## Testing

Automated tests use `RECEIPT_EXTRACTOR=fake` (`FakeExtractor`, synthetic results, labelled "Synthetic test
reading" in the UI) or a mocked Anthropic client. The test configuration blanks `ANTHROPIC_API_KEY`, so no
paid call can be made from the suite. **Live accuracy is only established by running the real adapter
on real receipts with founder-authorised credentials.**
