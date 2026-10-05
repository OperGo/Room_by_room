# Milestone 3 plan: everyday founder use and friction fixes (due 11 October 2026)

Prepared on 5 October 2026, while R2–R5 samples are unavailable. Milestone 3 starts once Milestone 2's evidence
is in (target 8 October). It is not a feature sprint: the founder uses the app for real, and fixes are limited
to friction found in that use.

## What the founder does (2–3 days, about 10 minutes a day)

Use the app as you would for the renovation, on your phone, and note anything slow, confusing or wrong.
- Add each new receipt as it happens: upload, Read, check, allocate, confirm.
- Add shopping-list items for upcoming jobs; tick them off when bought.
- Check a project's costs against what you expect.
- Open the app after it has been idle (morning, or after lunch) and note how long it takes to appear.

Never send receipts or photos, only notes.

## Friction log (one line per issue)

```
F#: date/time | screen | what I did | what happened | what I expected | blocks me / annoying / minor
```

Example: `F1: 9 Oct 08:10 | Home | opened app | blank for ~50 s | opens in a few seconds | annoying`

## Triage (Claude proposes, CTO decides)

| Class | Meaning | Handling |
|---|---|---|
| Blocker | Wrong money, lost data, cannot complete a task | Fix first; one PR each |
| Fix in M3 | Repeated friction with a small, local fix | Batched into small PRs by 11 October |
| Defer | Nice to have, or needs design work | Recorded in the ledger for after go-live |
| Founder decision | Material product/UX change or new spending | Routed through the CTO with a recommendation |

Every fix follows the release loop (`AGENTS.md`): one bounded PR into `sprint-2a`, CI green, CTO review, merge,
auto-deploy, CTO verification. Template, CSS or JavaScript changes also run the Playwright browser suite.

## Known candidates before founder use

| # | Item | Evidence | Options | Recommendation |
|---|---|---|---|---|
| K1 | **Cold start of the free web service.** After 15 minutes without traffic the service sleeps; the next visit takes about a minute. | Render free-tier behaviour (documented); not yet measured on this service | (a) keep free and accept the wait; (b) Render Starter web, **+US$7/month** (new spending: founder decision via the CTO) | Measure first: the founder logs wake times in the friction log for 2–3 days. Decide on day 3 with real numbers. |
| K2 | **Sign-in page looks phone-sized on a laptop.** Founder remark, 4 October. | The sign-in card is deliberately limited to 380 px wide and centred (`static/css/app.css`, `.login-card`); signed-in pages use the full desktop layout. | (a) keep; (b) small polish (wider card, or a short welcome panel beside it on desktop) | Low priority: it is the sign-in screen only. Take (b) only if the founder still finds it confusing in daily use. Minor UX, so a CTO decision, not a founder one. |
| K3 | **Waiting for a reading.** Cron cadence gives roughly 1–2 minutes; the page polls and fills values in; a waiting message appears after 5 minutes. | R1: 11 s (one observation) | — | Watch only; act if the founder logs waits over 2 minutes. |

## Outputs at the end of Milestone 3
- The friction log with triage outcome per item.
- The merged fix PRs, each with its merge SHA and the CTO-verified deployed SHA.
- The K1 decision (free vs Starter web), with measured wake times.
- An updated delivery ledger and a Milestone 3 report in `docs/sprints/`.
