# Consolidated owner test session — Saturday 10 October, morning (Milestone 2 evidence and new checks)

One attended session of about 45–60 minutes. It collects all remaining Milestone 2 evidence in one sitting:
R2–R5, the controlled failure check, `receipt_jobs` metadata, API spend and the cron cost.

**The cron command is never changed unattended.** The CTO's connector cannot change cron commands, so the
dashboard edits below are made by whoever is at the Render dashboard during the session, normally the
founder, with the CTO following along. Nothing secret is pasted into chat: only the sanitised log lines named
below.

## Before the session

- R2–R5 documents to hand. Mixed documents are allowed: delivery or discount, a two-project split, an imperfect
  photo, and a PDF or typical receipt.
- The R1 photo, used for the disposable failure and restoration drafts.
- Render dashboard open on the cron job `room-by-room-receipts` (Settings → Command), and the Anthropic
  Console open.

## Minimum dashboard actions (cron command only; save after each)

| # | Set the command to | Why |
|---|---|---|
| D1 | `python manage.py receipt_jobs --limit 200` | Empty-queue proof |
| D2 | `env ANTHROPIC_API_KEY=invalid-pilot-test-key python manage.py process_receipts --once` | Controlled failure |
| D3 | `python manage.py process_receipts --once` (exactly) | **Restore** |
| D4 | `python manage.py receipt_jobs --limit 200` | Metadata for every job |
| D5 | `python manage.py process_receipts --once` (exactly) | **Restore** |

**Restore always:** if anything fails, stalls or the session is interrupted after D1, D2 or D4, set the exact
normal command (D3/D5) immediately. Then confirm that a run started after the save logs `Claimable at
start: …` and `Processed …`.

## Sequence

1. **Pause uploads.** The owner does not upload or tap Read until told.
2. **D1, then read the next run's log.** The queue is empty only if:
   - the "Recent jobs" table has fewer rows than 200, so it is the complete table; and
   - no row is `queued` or `processing`.
   If either fails, stop: do D3 and report.
3. **D2, then wait for one run after the save.** It should log `Claimable at start: 0 job(s)`.
4. **Owner:**
   - upload the R1 photo as a **new** draft and tap **Read receipt automatically**;
   - record that the page shows "Couldn't read this receipt", that manual entry is available, and that
     Costs is unchanged;
   - leave the draft unconfirmed.
   The log shows one run with `Processed 1 job(s)`, and the next shows `Claimable at start: 0 job(s)` (no
   retry).
5. **D3 (restore), then verify a normal run.**
6. **Owner:** upload the R1 photo again as a new draft and tap Read. The values should appear, which proves
   the stored key is in use. Leave it unconfirmed; it is diagnostic only.
7. **Owner: R2–R5.** For each document:
   - start from the right project's **Costs → Add receipt**, then upload and tap Read;
   - check every value against the paper;
   - use **Assign** for single-project receipts;
   - split R3 between the two projects;
   - confirm, then check that Costs is exact.
   Note the time from tapping Read to the values appearing, the values that were correct, and each
   correction.
8. **D4, then read the next run's log.** Copy the complete table (job numbers, states, attempts, timings,
   model and tokens only).
9. **D5 (restore), then verify a normal run.** Resume normal use.
10. **Costs:**
    - Anthropic Console, Room by Room workspace: amount consumed and remaining balance (purchased US$5.00).
    - Render: the cron job's billed amount, plus the elapsed period from the cron job's creation time to now.
      This gives a 30-day projection, checked against the US$5/month threshold.

## Additional checks (CTO plan of 7 October; include each only if its PR is released by Saturday)

These come after step 9, when the normal command is restored and uploads have resumed. Mark any check whose
release is not live as **not run**. It must not be recorded as passed.

11. **Home project costs** (PR "Home project financial visibility").
    - On Home, each project card shows **Recorded £…** and, where a budget is set, **£… left of £… budget**
      or **£… over the £… budget**. A project without a budget says **No budget set**.
    - After R2–R5, check that each project's Home figure matches its project page (Spent) to the penny.
    - Check that unconfirmed drafts do not change it.
12. **Unsaved receipt changes** (PR "Receipt-review unsaved edits").
    - On a draft, type a value or tap **Assign**: an **Unsaved changes** indicator appears.
    - Tap **Costs** (back): the browser warns before leaving.
    - Save or Confirm: no warning appears.
    - On iPhone this warning is best effort and may not show when closing the tab. Note what happened.
13. **Reading connection feedback** (PR "Receipt-reading connection feedback").
    - While a reading is waiting, turn on airplane mode for about 30 seconds: a connection message appears.
    - Turn airplane mode off: the message clears, typed values are unchanged and no purchase is created.

## What to send back

```
Session date/time (UTC):
D1 empty-queue proof: rows __ (<200) ✓/✗, no queued/processing ✓/✗
Failure: message ✓/✗, manual entry ✓/✗, Costs unchanged ✓/✗, no retry ✓/✗
Restored (D3) + normal run ✓/✗; re-read values appeared ✓/✗
R2 delivery/discount: read in __ s; correct: __; corrections: __; Costs exact ✓/✗
R3 split: read in __ s; correct: __; corrections: __; project A ✓/✗ project B ✓/✗
R4 imperfect photo: read in __ s; correct: __; corrections: __; Costs exact ✓/✗
R5 typical/PDF: read in __ s; correct: __; corrections: __; Costs exact ✓/✗
D4 receipt_jobs log: [pasted]
Restored (D5) + normal run ✓/✗
API: consumed $__ of $5.00, balance $__
Cron: created __ (UTC), checked __ (UTC), billed $__
Home costs match project pages ✓/✗/not run; drafts excluded ✓/✗/not run
Unsaved-changes indicator ✓/✗/not run; leave warning ✓/✗/not run; no warning on Save/Confirm ✓/✗/not run
Connection message offline ✓/✗/not run; cleared online ✓/✗/not run; values kept ✓/✗/not run
```
