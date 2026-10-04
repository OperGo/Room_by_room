ROOM BY ROOM — MILESTONE 1 PREFLIGHT CORRECTIONS REPORT TO CHATGPT CTO
Date: 5 October 2026
Current milestone: 1 (accepted), preflight corrections complete. Milestone 2 starts after the founder's budget approval and confirmation of the dashboard quotes.
Status: all five corrections are applied in docs/receipt-runtime-decision.md, plus one small application change (the waiting message) with a focused check. No paid resources, credits, keys, live calls or deployments.

1. OUTCOME
1. Costs corrected.
   - Cron is priced at Render's published US$0.00016/minute: at 43,200 runs a month, 10–30 s per idle run gives US$1.15–3.46.
   - Infrastructure total: **US$7.50–9.80/month** before tax and API use (US$6.30 database plus cron). A paid web service would add US$7.
   - The founder confirms the actual dashboard quotes before starting.
2. Key activation corrected.
   - Cron job: add ANTHROPIC_API_KEY, then "Save, rebuild, and deploy" (or "Save and deploy"). The guide states that "Save only" does not apply it to the next run.
   - Web service: "Save, rebuild, and deploy", or "Save only" followed by Manual Deploy → Deploy latest commit. Then confirm the deployed commit is the final tested SHA.
   - Both services deploy that SHA.
3. One concrete `receipt_jobs` procedure.
   - Use the Shell if one exists.
   - Otherwise:
     1. Pause uploads.
     2. Wait until no run is active (don't Trigger Run during an active run; Render cancels it).
     3. Set the cron command to `python manage.py receipt_jobs --limit 20`, then save and deploy.
     4. Copy the next scheduled run's sanitised log.
     5. Restore `python manage.py process_receipts --once`, then save and deploy.
     6. Confirm the next run logs "Claimable at start", then resume.
   - No extra service and no credentials in chat.
4. Waiting time.
   - "At worst about two minutes" is replaced with an ordinary first-attempt target of **roughly 1–2 minutes**.
   - Retries, backlog and recovery can take longer, and each is explained.
   - The misleading message is fixed (see section 2).
5. Spending boundaries are explicit:
   - the cron US$5/month projection is a monitoring threshold, not a billing cap: suspend the cron job and report;
   - the database keeps billing if the cron trial stops;
   - the Anthropic monthly workspace limit is US$5;
   - a separate **total Milestone 2 API testing allowance of US$5** is tracked on the Console's usage page;
   - credits: auto-reload off, report any minimum purchase above the allowance;
   - a dedicated worker or a paid web service needs separate approval.
   The guide also states that managed backups do not replace Milestone 4's recovery check, and that the no-manual-backup decision still stands for the disposable preview.
- The guide also contains the Milestone 2 evidence protocol: R1–R5 receipt types (aiming for at least four useful drafts), per-receipt timing and corrections, the six once-only checks, actual API spend and the cron usage after 24 hours.

2. SCOPE
Delivered:
- docs/receipt-runtime-decision.md (rewritten); the deployment-render.md overview row (accepted, US$7.50–9.80).
- Application change: RECEIPT_STALE_QUEUE_SECONDS 120 → 300. The message now reads "Still waiting. Readings normally start within 1–2 minutes. If nothing changes soon, enter the details yourself or try again later." The old wording ("…worker may not be running…") is removed.
- Tests: 1 new test function (the waiting message must not appear at 150 s, must appear at 301 s, and the page shows the new wording); the checklist guard test is extended.
Deferred/incomplete, with reasons: Milestone 2 itself (awaiting founder approval).
Departures from CTO brief, with reasons: none. The waiting-message correction is applied now so that the single Milestone 2 deploy carries it.

3. CODE AND SETUP
- Branch sprint-2a.
- 53d6eae: preflight corrections, waiting message and tests; then this report commit (documentation only).
- **Final tested SHA** for the cron job and the web service: the branch head named in the handoff message. Its application files are identical to 53d6eae.
- Pushed normally; the remote SHA is verified against HEAD in the handoff message.
- No PR, merge or deploy.

4. VALIDATION
Checks actually run and results:
- `pytest tests/test_free_preview_config.py tests/test_reading_jobs.py` → 39 passed. This includes the new waiting-message test and the extended guide guard (costs, rate, the "Save only" warning, the receipt_jobs swap procedure, boundaries and the 1–2 minute target).
- Not repeated: the full SQLite/PostgreSQL/browser suites. Only a threshold constant and one template sentence changed; no logic or layout changed.
Screens inspected: none (text-only change, covered by the test).
Not verified: hosted performance, billing, the dashboard labels ("Save, rebuild, and deploy", Runs page) and live extraction. These are Milestone 2 evidence.

5. COST INTEGRITY
Unchanged.

6. RECEIPT PROCESSING
Unchanged adapter; mocked SDK only. Live accuracy is unproven.

7. RISKS / DECISIONS FOR CTO
Acceptance evidence: Milestone 1 was accepted at adf25b9. These preflight corrections are listed above.
Remaining launch blockers:
- the founder's budget approval and quote confirmation;
- Milestone 2's five live receipts and its evidence (8 October);
- the everyday-use review (11 October);
- retained-data readiness with a recovery check (14 October);
- final validation and the founder-authorised go-live (16 October).
Estimated remaining effort:
- Milestone 2: about 2 h founder plus about 3 h Claude;
- Milestone 3: 2–3 days of use plus 4–8 h fixes;
- Milestone 4: 2–3 h;
- Milestone 5: about 2 h.
Effect on 16 October: on track if approval and setup happen by 6–7 October.

8. FOUNDER REVIEW
- Approve (or amend) the budget:
  - about US$7.50–9.80/month infrastructure;
  - a US$5 monthly API limit and a US$5 total testing allowance;
  - the database keeps billing if the cron trial stops.
- Then confirm the quotes and follow the checklist in docs/receipt-runtime-decision.md.
