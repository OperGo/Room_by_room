# DESIGN.md — Room by Room

## Reference status
The four founder-approved mockups are stored in `docs/mockups/` (`home.png`, `project-detail.png`,
`review-receipt.png`, `shopping-list.png`) and are the primary visual target. A fidelity pass was made
against them at 390px (see "Mockup comparison" below).

Inspiration (not overriding the approved mockups): Jira summary (Home), Angi project detail
(Project), Splitwise receipt review (Receipt review), Alexa shopping list (Shopping). No Sarre & Company
or Sunday.je styling is used.

## Tokens (`static/css/app.css` `:root`)
| Token | Value | Use | Contrast |
|---|---|---|---|
| `--bg` | #F7F5F0 | warm ivory page | — |
| `--primary` | #23483C | forest green actions, active nav | white on it 10.2:1 |
| `--text` | #202923 | charcoal body text | 13.7:1 on ivory |
| `--sage` | #DCE5DA | supporting surface, active nav pill, progress track | primary on it 7.9:1 |
| `--card` | #FFFFFF | data surfaces | — |
| `--muted` | #59645E | metadata | 5.65:1 on ivory, 6.2:1 on white |
| `--ochre` / `--ochre-tint` | #8A6417 / #F5EBD3 | draft & warning labels | 4.52:1 |
| `--error` / `--error-tint` | #A3352A / #F8E4E0 | errors, over budget | 5.54:1 |
| `--line` | #E4E1D8 | thin dividers | — |
| radii | 8 / 14 / 20 px, pills 999px | rounded controls | — |
| shadow | 0 1px 2px rgba(32,41,35,.05) | minimal | — |

Typography: Inter variable (OFL, served locally from `static/fonts`), falling back to the system
sans-serif stack. No font CDN. Body 16px, metadata 14px, h1 28–30px/700.

Icons: Lucide (ISC licence), inlined as an SVG sprite (`templates/includes/icon_sprite.svg`), 1.75
stroke. No emoji.

## Components
Buttons (primary pill, secondary outline, sage, ghost, danger; min 44px), icon buttons (44×44),
cards with thin borders, list rows (title + metadata + trailing amount/chevron), status badges with text
(Active, Draft · not counted, Void, Refund, Blocked, This weekend, Estimate), progress bars (task
progress; budget used, labelled as not progress), tabs, segmented control (Shopping grouping), stat
tiles, alerts (error/warning/info/success, each with icon + text), purchase editor (lines, type,
category, quantity, optional unit price, line total, destinations with amount splits, live
reconciliation bar), evidence panel, upload option tiles, data tables (desktop costs).

## Responsive rules
- **< 768px (phone, designed at 390px):** single column, 20px gutters, fixed bottom navigation (Home,
  Projects, Shopping, Costs) with the active destination marked (`aria-current`), content padded clear
  of the nav, natural vertical scroll, sticky primary action above the nav on long forms.
- **768–1023px:** 28px gutters; two-column splits where helpful (project hero + stats, receipt evidence
  + editor, shopping list + bought), four stat tiles in a row.
- **≥ 1024px (desktop, checked at 1440px):** left sidebar rail with brand, nav, Add receipt and sign
  out; bottom nav hidden; cost tables instead of row lists; receipt review shows sticky evidence on the
  left and editable details on the right.
- No phone bezel or fake OS chrome; no whole-page scaling.

## Sample imagery
The seeded Office cabinetry and Hallway covers are cropped from the approved **generated** mockups
(`apps/core/seed_assets/`). They are labelled "Sample image" in the UI and are not photographs of the
founder's home. The seeded receipt is a synthetic image marked
"SAMPLE RECEIPT – NOT A REAL PURCHASE". Neither depicts the founder's home or a real purchase.

## Screenshot evidence (Sprint 1)
Real Chromium renders of the seeded demo account, in `docs/screenshots/` (`<screen>-<width>.png` is
the first viewport; `-full.png` is the full page — in full-page captures the fixed bottom nav appears
mid-page, which is a capture artefact, not a layout bug).

Screens: `home`, `projects`, `project`, `project-costs`, `shopping`, `costs`, `purchase`,
`add-receipt`, `receipt-review` at widths 390, 768 and 1440.

Fixed after inspection: task titles and metadata ran together on one line; stray leading "·" in task
metadata; the receipt image filled the whole first screen on phones (capped at 46vh); the Total field's
placeholder was cut off.

## Mockup comparison (fidelity pass, 390px)
Matched: wordmark + round add button header; date eyebrow, "Make room for progress" headline and
subtitle; featured project card (photo, title + chevron, "n of m tasks complete", thick progress bar);
compact project cards with photo on the left; "Ready this weekend" / task cards with ring checkbox,
clock + tag metadata and chevron; full-width primary actions ("Add a receipt", "Add a task", "Add an
item") kept reachable above the bottom nav; bottom nav with solid active icon, green label and no pill
(Home, Projects, Shopping, Costs); project page "< Projects" back link, progress above photo, sage
Spent | Budget panel, equal-width underlined tabs, "Next steps", blocked tasks shown as "After …",
completed tasks as sage cards; shopping full-width "By project | By shop" toggle, uppercase sage group
bars with counts, plain divided rows, collapsible "Bought (n)" section and the "Bought items do not
record a cost automatically" note; receipt review "< Costs", draft badge with dot, receipt thumbnail
beside Merchant / Date / Total, "Items & projects" cards with project picker, "Allocated £x of £y" bar
with tick, "Retake photo" + "Confirm purchase".

Intentional differences:
- Amounts keep pence (£115.60, £1,200.00); the mockup rounds to pounds. Money accuracy wins.
- Extra honest labels: "Sample image", demo-account badge, "Draft · not confirmed" (mockup: "not
  saved"), budget left/over note, the explanation that Spent is confirmed cost and not proof of payment.
- Extra controls the brief requires: edit pencil on the project title, record-purchase button on each
  shopping item, "Type, quantity or split" disclosure on receipt items, attach/discard section.
- Receipt item fields are always-visible inputs rather than text with pencil icons (clearer on touch and
  for screen readers). Destinations use a tag icon rather than per-room icons.
- "Ready this weekend" appears only when tasks have been planned for the weekend; otherwise the honest
  heading is "Ready to start".
- "Retake photo" discards the draft (no cost) and returns to Add receipt.
- Font is Inter (locally served); the mockups use a similar geometric sans.
- Desktop layouts are not in the mockups; they follow the responsive rules above.

## Sprint 1A corrections
- Editor copy: "Purchase total (£, GBP)"; essential guidance only ("Items must add up to the purchase
  total…"); tax note moved into the Description and notes disclosure; the derived total is shown in the
  Allocated bar when the total is left blank.
- Receipt review (phone): compact header (draft badge + one-line extraction note), thumbnail beside
  Merchant/Date/Total, item cards with amount and project in the main row; type, category, quantity,
  unit price, split and remove inside "Type, quantity or split". Split rows stack project above amount
  below 600px.
- Focused fields: on phones the sticky actions return to normal flow and the bottom nav hides while a
  field has focus; `scroll-padding-bottom` keeps focused fields clear (browser-tested).
- Project: no budget bar or explanatory paragraph; status badge only when not active; shorter cover;
  ready jobs listed before blocked ones.
- Shopping: retailer shown in the project grouping (the project is shown in the shop grouping).
- Demo label reduced to a small "Demo · fictional data" tag.
- All controls on the four key screens measure at least 44×44px (browser-tested).
