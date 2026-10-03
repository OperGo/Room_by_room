# Receipt processing

## Sprint 1 (current)
- Upload choices: **Take photo** (`capture="environment"`), **Upload image** (JPEG/PNG/HEIC/HEIF),
  **Upload PDF**, or **Manual entry** (no file needed).
- Validation (`apps/core/uploads.py`): content signature (not extension), 15 MB per file, 50 megapixel
  decode limit (decompression-bomb guard), PDFs readable, not password-protected, ≤ 5 pages.
- Storage: original kept privately; HEIC gets a JPEG preview for browsers. SHA-256 checksum stored.
- A `ReceiptDraft` is created with empty values. The review screen shows the original beside the
  editor. The UI states that automatic extraction is not available yet; nothing is sent to any AI provider.
- The owner either **confirms** (posts exactly one purchase, idempotent), **attaches** the receipt to an
  existing purchase (evidence only, no cost), saves the draft, or discards it.
- Exact-duplicate uploads (same checksum) show a warning; they are not blocked.

## Extraction boundary (ready for Sprint 2)
`apps/receipts/extraction.py` defines `ReceiptExtractor.extract(document) -> ReceiptExtractionResult`
(merchant, date, currency, total, receipt number, lines with optional quantity and line total, uncertain
fields, warnings, model version, usage). `ExtractionJob` stores status, adapter/model, attempts, lease,
draft JSON, warnings, sanitised error and usage, with a partial unique constraint allowing only one
queued/processing job per document.

## Planned for Sprint 2 (not implemented)
Anthropic API adapter using server-side `ANTHROPIC_API_KEY` and `RECEIPT_MODEL` (model and limits to be
verified at implementation time); `process_receipts --once/--watch` worker with transactional claiming,
lease recovery and bounded retries; UI polling; server-side normalisation and reconciliation;
probable-duplicate warnings (merchant/date/total) with acknowledgement; fake adapter for tests.
If no key is configured the UI says "Automatic extraction not configured" and manual review still works.
