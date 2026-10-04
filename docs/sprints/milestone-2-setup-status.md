ROOM BY ROOM — MILESTONE 2 STATUS UPDATE TO CHATGPT CTO (setup complete; live receipts not yet started)
Date: 5 October 2026
Current milestone: 2 (five live receipts through accurate confirmed costs; target 8 October). Hosted setup is done within the approved scope. **No live receipt has been read yet.** I paused at the founder's request to update the CTO before the five-receipt protocol.

1. OUTCOME (all founder-reported; I have no Render or Anthropic access, and onrender.com is blocked from my environment)
- Quotes confirmed before purchase:
  - Render cron Starter (0.5c-512mb): US$0.00016/min (founder's dashboard screenshot), as approved;
  - Anthropic minimum credit purchase: US$5, equal to the approved US$5 testing allowance.
- Database: the existing PostgreSQL 18 was upgraded in place to the paid plan, which the founder reports as US$6/month. Storage (about US$0.30) is expected on top, so about US$6.30, within approval. `/healthz/` remains ok after the upgrade.
- Anthropic: a dedicated "Room by Room" workspace was created and US$5 of credit bought. A key `room-by-room` was created and stored in the founder's password manager; it has not been shared.
  - Advised: a monthly spend limit of US$5, auto-reload off, and a 90-day key expiry with a rotation reminder (expiry fails safely to manual entry).
  - **To confirm:** the spend limit and auto-reload settings, and the expiry chosen.
- Cron job `room-by-room-receipts` created: Frankfurt, Starter, schedule `* * * * *`, build `pip install -r requirements.txt`, command `python manage.py process_receipts --once`, the seven listed environment variables (Internal DATABASE_URL), deployed commit **c85e964** (confirmed by the founder).
  - First scheduled run, **without** a key: "Automatic extraction not configured …", "Claimable at start: 0 job(s)", "Processed 0 job(s).", "run finished successfully". So no earlier receipts could be sent.
  - After ANTHROPIC_API_KEY was added with save-and-deploy: "Claimable at start: 0 job(s)", "Processed 0 job(s).", finished successfully, with the "not configured" line gone. The key is active on the cron job.
- Web service: `/healthz/` reports ok.
  - **To confirm:** that ANTHROPIC_API_KEY is on the web service, deployed at c85e964 (which also carries the corrected 5-minute waiting message), and that the "Read receipt automatically" button now appears.
- Spend so far: Render database (billing from the upgrade) and cron (per-second, idle runs only). API spend is US$0, since no reading has run.

2. SCOPE
Delivered since the preflight report (c85e964): founder-applied setup only. No code changes. This status note is committed for the record.
Not started: R1–R5, the six once-only checks, receipt_jobs evidence collection, the 24-hour cron usage check, and the actual API spend.

3. CODE AND SETUP
- Repository: branch sprint-2a; hosted services at c85e964 (the cron job is confirmed; the web service is to be confirmed). This note is committed on top (documentation only); its SHA is given in the handoff message.
- No PR, merge or extra services. The free web service is kept.

4. VALIDATION
Founder-reported:
- the quotes above;
- the database upgrade with /healthz/ ok;
- the two cron run logs quoted above, with the deployed commit c85e964.
My own checks: none of the hosted service (no access). The earlier local tests at c85e964 stand (39 focused passes).

5. COST INTEGRITY
No live reading or confirmation has happened yet; nothing new to evidence.

6. RECEIPT PROCESSING
Live adapter configured (Haiku 4.5 `claude-haiku-4-5-20251001`). Zero live calls so far.

7. RISKS / DECISIONS FOR CTO
- Monitoring: the cron 24-hour usage check is due about 24 hours after the cron job's creation (the founder notes the time). Suspend and report if it projects above US$5/month.
- Pending confirmations before R1: the web key and deploy, the Read button, and the Anthropic spend limit, auto-reload and expiry settings.
- Ready to run: the five-receipt protocol (R1 itemised; R2 delivery/discount; R3 split across two projects; R4 imperfect photo; R5 typical or PDF) with the once-only checks and receipt_jobs collection, as in docs/receipt-runtime-decision.md.
- Effect on the 8 October target: on track if the receipts run on 6–7 October. 16 October unchanged.
Remaining launch blockers: Milestone 2 evidence; Milestone 3 everyday-use review; Milestone 4 retained-data and recovery check; Milestone 5 final validation and go-live authorisation.
Estimated remaining effort: Milestone 2 about 1.5 h founder plus about 2 h Claude (evidence and report); the later milestones as previously estimated.

8. FOUNDER REVIEW
Awaiting the CTO's next instructions before starting R1.
