# Room by Room

A phone-first organiser for home renovation: what is left to do, what do I need, and what has it cost?
Django 5.2 LTS · Python 3.13 · server-rendered templates with small progressive JavaScript.

Status: **Sprint 2** (see `docs/sprints/`). Receipts can be uploaded, read automatically by the Anthropic
API (when `ANTHROPIC_API_KEY` and `RECEIPT_MODEL` are configured), reviewed and confirmed. Live accuracy on
real receipts has not been verified yet. See `docs/receipt-processing.md`.

## Local setup

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # DJANGO_DEBUG=1 for local use
python manage.py migrate
python manage.py create_owner alistair      # your real, empty account (prompts for password)
python manage.py seed_demo --password 'choose-a-demo-password'   # optional disposable demo account
python manage.py runserver 0.0.0.0:8000
```

- SQLite is used when `DATABASE_URL` is unset. It is fine for a single local user but it does not
  provide row locks; concurrency guarantees are only tested and supported on PostgreSQL.
- PostgreSQL: `DATABASE_URL=postgres://user:pass@host:5432/roombyroom`.
- `seed_demo` is idempotent: it never overwrites existing demo data unless `--reset` is passed, and it
  refuses to touch non-demo accounts. The real account starts empty.
- There is no public signup and no Django admin.
- Receipt worker (separate process, needed for automatic reading):
  `python manage.py process_receipts --watch` (or `--once` from cron). Set `ANTHROPIC_API_KEY` and
  `RECEIPT_MODEL=claude-haiku-4-5` in `.env`; without them the app says extraction is not configured.

## Tests

```bash
pytest                                                     # unit/integration on SQLite
DATABASE_URL=postgres://... pytest                         # + PostgreSQL concurrency tests
pytest tests/browser -o addopts="" -p no:cacheprovider     # Playwright (Chromium) browser suite
python scripts/screenshots.py --password <demo password>   # regenerate docs/screenshots (server running)
RECEIPT_EXTRACTOR=fake python scripts/screenshots_sprint2.py --password <demo password>  # synthetic reading states
```

## Layout

| Path | Contents |
|---|---|
| `apps/core` | money/date helpers, private storage, upload validation, audit trail (`ChangeEvent`), home |
| `apps/projects` | projects, tasks, dependencies, photos (`services.py`: `complete_task`, `set_dependencies`) |
| `apps/shopping` | shopping list |
| `apps/costs` | purchases, lines, allocations, refunds, opening balances (`services.py`, `selectors.py`) |
| `apps/receipts` | receipt documents, drafts, extraction boundary |
| `templates/`, `static/` | UI, design tokens in `static/css/app.css` |
| `docs/` | architecture, receipt processing, sprint reports, screenshots |

## Deployment

Prepared for Render but **not deployed**: see `render.yaml` and `docs/deployment-render.md`. Real hosting needs HTTPS (`DJANGO_HTTPS=1`), PostgreSQL, a private file store,
and tested backups/restoration of both database and private files. This repository is a local build,
not a production deployment.
