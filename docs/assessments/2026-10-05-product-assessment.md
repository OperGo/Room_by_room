# Product and implementation assessment (5 October 2026)

For the CTO's prioritisation before the 16 October founder go-live. No application code was changed.

## Method and evidence labels

- **Local build**: branch `sprint-2a` at `6ceefd6` (the verified deployed commit). It ran on Django's local
  server with SQLite and was seeded with `seed_demo`, the fictional Office/Hallway demo. A second, empty
  account was used for empty states.
- **Screens**: real Chromium (Playwright) captures at **390, 768 and 1440 px**. The 390 and 768 captures use
  a phone/tablet profile with touch. Sixteen representative captures are in `docs/assessments/2026-10-05/`
  (390/768 downscaled to 1×). The full set (about 160 files) and per-page metrics stayed local.
- **Screens covered**:
  - sign-in (and its error state);
  - Home, Projects, Project (Tasks, Costs and Photos tabs);
  - Shopping (by project and by shop);
  - Costs, purchase detail, add purchase, add task, add item, add project;
  - Add receipt;
  - receipt review in four states: new, waiting, read, and wrong total / unallocated;
  - reading failure;
  - empty Home, Projects, Shopping and Costs.
- **Automated per-page checks**: horizontal overflow, page height, and interactive elements under 44 px.
- **Receipt evidence labels**:
  - "read" states come from the **fake test extractor** (mocked provider; synthetic values);
  - the failure state comes from a **local** worker run without a key (`not_configured`);
  - **live provider** evidence is R1 only, which is **founder-reported** (11 s, merchant, total and 3/3
    items correct).
- **Scope baseline**: the original build brief text is not in the repository. Scope was checked against the
  sprint reports' delivered and deferred lists (Sprints 1–2C) and `DESIGN.md`.

## What works well and should be preserved

- **Money integrity is visible.** Screens show "Draft · not confirmed / not counted". A failed confirmation
  says "Nothing was recorded" and keeps every entry. "Recorded cost is not a bank ledger" is explained, and
  estimates are labelled ("incl. £850.00 estimates").
- **Receipt recovery paths are clear.**
  - The waiting state says you can keep typing.
  - The failure state offers "Try reading again" with manual entry still visible.
  - The duplicate-file warning links to the earlier drafts.
  - "Already recorded this purchase? Attach" avoids double counting.
- **Layout is solid on phones.**
  - **No horizontal overflow** on any captured page at any width.
  - Bottom nav with clear active state; one primary action per screen, kept above the nav.
  - Inputs and buttons are at least 44 px. Only inline text links inside tables and alerts are smaller,
    which is acceptable.
- **Empty states guide the next step**, for example "No active projects yet → New project" and "Nothing
  ready yet. Add tasks…".
- **Visual system is consistent**: ivory/forest/sage tokens, the Inter type scale, and cards. It matches the
  approved mockups at 390 px. Desktop has a proper sidebar and data tables.
- **Planning is useful**: "Ready to start" with blocked tasks shown as "After …", progress per project, and
  a shopping list grouped by project or shop with an honest "Bought items do not record a cost" note.

## Missing approved scope

**None found.** Every Sprint 1 and Sprint 2 deliverable listed in the reports is present and works in the
local build:
- projects, tasks, dependencies, weekend plan, photos;
- the shopping list;
- manual purchases, splits, refunds, voids and opening balances;
- costs views;
- receipt upload, reading, review, confirmation, attaching, duplicate warnings and the worker.

The approved deferrals stand: no offline mode, a basic manifest only, and no public signup. The gaps below
are **usability and finish defects within delivered features**, not missing features. None of them is a new
feature proposal, except where marked.

## The five highest-value gaps (ranked by user impact)

### 1. Receipt allocation takes one project choice per line, and project context is lost

- **Evidence (local, fake extractor):**
  - After a reading, each of the 5 lines shows its own "Choose project…" select (`receipt-read-390-full.png`).
  - Confirming without choosing lists 5 identical errors, "Line n: Choose where this cost belongs"
    (`receipt-wrong-total-390.png`).
  - "Add receipt" on a project's Costs tab links to `/receipts/new/` without the project
    (`templates/projects/detail.html:73`). "Add purchase" on the same tab does pass `?project=`.
  - There is no "all items to one project" control (`static/js/app.js`, templates).
  - For the founder, most receipts belong to one room (Office or Hallway), so every receipt costs N extra
    taps. This is the most frequent action in the app.
- **Proposal:**
  - Add an "Assign all items to: [project ▾]" select above "Items & projects". It fills every line that has
    no destination yet; per-line choice and splits are unchanged.
  - Starting a receipt from a project pre-selects that project for the draft.
  - Collapse the repeated errors into one line, for example "Choose a project for 5 items".
  - Server rules are unchanged: allocations are still validated per line in `apps/costs/services.py`.
- **Screens**: receipt review, manual Add purchase (same editor), project Costs tab link.
- **Effort**: about 4–6 h, including a browser test.
- **Acceptance criteria:**
  - From a project page, upload → read → confirm needs **no** per-line project choice when all items
    belong to that project.
  - The bulk select never overwrites a line already set or split.
  - Totals, reconciliation and refusal rules are unchanged (existing tests pass).
  - One consolidated error replaces N repeats.
  - No overflow at 390/768/1440.
- **Classification**: **fix before launch**. It is a minor UX addition inside the approved receipt
  workflow, so I recommend treating it as routine (CTO decision). It does not change product behaviour or
  money rules.

### 2. Free web service cold start (unmeasured)

- **Evidence**: Render's free tier sleeps after 15 minutes idle, and the first request takes about a minute
  (documented; `docs/deployment-render-free-preview.md`). It has **not been measured** on this service; no
  production evidence yet.
  - It affects the first open of every session.
  - It hits the moment of use: in a shop, or with a receipt in hand.
- **Proposal**: measure during Milestone 3. The founder notes wake times in the friction log
  (`docs/milestone-3-plan.md`, K1). Then decide between keeping free and Render Starter web at +US$7/month.
- **Screens**: all (first load).
- **Effort**: no code. Switching is a dashboard change plus verification.
- **Acceptance criteria**: a decision recorded with measured wake times before 14 October.
- **Classification**: **decide before launch**. Paid web is **new spending**, so it needs **founder
  approval through the CTO**.

### 3. Sign-in page is broken at 1024 px and wider (laptop/desktop)

- **Evidence (local, 1440 px)**: the sign-in card is squeezed into a 120 px column at the left edge, with
  the text wrapping word by word (`signin-1440.png`). It is correct at 768 px (`signin-768.png`) and on
  phones.
  - **Root cause**: from 1024 px, `.app` becomes a two-column grid (232 px sidebar + content)
    (`static/css/app.css:375`). Signed-out pages have no sidebar (`templates/base.html:18`), so the content
    lands in the 232 px column.
  - This is what the founder saw on 4 October ("login screen on the laptop defaults to a mobile screen
    size").
  - Correction: `docs/milestone-3-plan.md` K2 called this deliberate; it is a layout bug, corrected in that
    plan.
- **Proposal**: apply the sidebar grid only when the sidebar exists, for example a class on `.app` for
  signed-in pages, or `.app:has(> .side-nav)`. Add a browser test at 1440 px.
- **Screens**: sign-in, and any signed-out page (sign-in error).
- **Effort**: about 1 h, including the test.
- **Acceptance criteria**:
  - At 1024 and 1440 px the sign-in card is centred and at most 380 px wide.
  - Signed-in desktop layout is unchanged.
  - Browser test passes.
- **Classification**: **fix before launch**. **Routine correction** (bug).

### 4. Form finish defects on everyday forms

- **Evidence (local, 390 px)**:
  - Duplicated "(optional)": the form labels already include it and `templates/includes/field.html` appends
    it again. This affects:
    - "Estimated minutes (optional) (optional)" and "Due date (optional) (optional)" on New task;
    - "Task (optional) (optional)", "Preferred retailer (optional) (optional)" and "Project (leave empty for
      shared) (optional)" on Add item;
    - "Room (optional)" on New project.
    - Sources: `apps/projects/forms.py:14,43`, `apps/shopping/forms.py:14`.
  - The empty Task select on Add item shows "---------".
  - On Add purchase (phone), the Merchant and Date labels sit at different heights, and the Merchant
    placeholder is cut off ("e.g. Timber merc").
  - On empty Home, the "New project" button's plus icon is invisible. `.empty .icon` (`static/css/app.css:271`)
  also styles icons inside buttons: the icon is drawn green on a green button, with an auto margin, so a gap
  shows where it should be.
- **Proposal**: remove the duplicate label text; use "No task" as the empty choice; align the Add purchase
  header row (stack Merchant and Date on phones); fix the button icon.
- **Screens**: New task, Add item, New project, Add purchase, empty Home.
- **Effort**: about 1–2 h.
- **Acceptance criteria**: no duplicated "(optional)" anywhere (template test); labels aligned at 390 px;
  existing browser tests pass.
- **Classification**: **fix before launch** (finish). **Routine correction.**

### 5. "Receipts to review" rows are indistinguishable

- **Evidence (local)**: on Costs, every draft row reads "Receipt · Uploaded <time> · <file name>"
  (`costs-1440.png`, `costs-390-full.png`). Merchant, total and reading state are not shown, even after a
  successful reading. Phone photos usually have similar or meaningless file names, so the founder cannot
  tell which draft is which without opening each.
- **Proposal**: when known, show the merchant and total from the draft, plus a short state: Waiting,
  Read · check, Couldn't read, or Draft. Keep the "Draft · not counted" label. This is a display change
  only; drafts still never count.
- **Screens**: Costs (phone list and desktop table).
- **Effort**: about 2 h, including tests.
- **Acceptance criteria**:
  - Rows show merchant/total/state when present and fall back to the current text otherwise.
  - No draft value appears in any total (existing selector tests pass).
- **Classification**: **fix before launch**, lower priority than 1–4. **Routine.**

### Considered and not ranked

- **Date inputs show mm/dd/yyyy in the captures.** That comes from the headless browser's US locale. The page
  is `lang="en-GB"`, and a UK phone shows dd/mm/yyyy. No change needed.
- **Inline text links under 44 px** (project names in cost tables, dates in the duplicate warning).
  Acceptable inside dense tables; not ranked.
- **No cost summary on Home.** Not in the approved mockups; it would be a new feature proposal, so it is not
  ranked.

## Recommended first implementation PR

**Gap 1: receipt allocation shortcut.** It has the highest everyday value, sits on the receipt workflow
that Milestone 2's R2–R5 exercise, and needs no new spending or data change. It is one bounded PR:
- the bulk "Assign all items to" select;
- project pre-selection from the project page;
- the consolidated error;
- browser tests at 390 and 1440 px.

**Then, in one small routine PR:** gaps 3 and 4 (sign-in layout bug and form finish). They are low risk
(template, CSS and form labels only) and could go first if the CTO prefers the quickest win.

Gap 2 needs the founder's measurements and a spending decision. Gap 5 follows when capacity allows.

## Access limitations

- **Production.** I have no access to production or Render, so cold start and production behaviour are not
  observed here.
- **Live provider.** No live provider calls are made from this environment. The receipt states shown are
  mocked (fake extractor) or local (not configured).
- **Founder inputs still needed.** Real reading accuracy and product preferences remain founder inputs (R2–R5
  and the Milestone 3 friction log).
