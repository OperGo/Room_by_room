# Deployment plan — Render (prepared, NOT deployed)

Target: the founder's existing Render project **"Room by Room"**. Nothing has been created, deployed or paid
for. `render.yaml` in the repository root is a Blueprint ready for review; applying it creates paid resources.
Resource creation, deployment and live API spending need explicit founder approval.

## Sources and how they were checked

The build environment's network policy blocks `render.com` and `api.render.com`, so the official pages could not
be opened directly. Facts come from:

- web-search extracts of official Render pages (October 2026);
- Render's official example repository `github.com/render-examples/django` (read directly);
- the official Render CLI source (`github.com/render-oss/cli`, commit `e864786`, 2 October 2026, built from the
  Go module proxy), whose generated API types list Render's current plan, Postgres-version and auto-deploy enums.

**Re-check prices on https://render.com/pricing and the dashboard quotation before applying.**

- Pricing: https://render.com/pricing
- Compute plans: https://render.com/docs/compute-plans
- Blueprint fields: https://render.com/docs/blueprint-spec
  - `autoDeployTrigger`: `commit` | `checksPass` | `off`.
  - `diskSizeGB`: 1 or a multiple of 5; it can grow but never shrink.
  - `postgresMajorVersion`: a string.
  - `storageAutoscalingEnabled`: when true, storage grows by 50% at 90% full.
- Projects and environments: https://render.com/docs/projects
- Persistent disks: https://render.com/docs/disks
- Postgres backups, PITR and exports: https://render.com/docs/postgresql-backups
- Free tier: https://render.com/docs/free
- Deploys, SIGTERM and shutdown delay: https://render.com/docs/deploys

## Key constraint and storage decision (approved)

A Render persistent disk belongs to exactly one service and cannot be read by another. The web service and
the receipt worker are separate services, so private receipts and photos are stored **in Render Postgres**
(`PRIVATE_STORAGE_BACKEND=database`, table `core_storedfile`):

- They are served only by owner-checked views.
- The same backups cover them as the financial data.

Uploads are at most 15 MB. iPhone photos are typically 1–4 MB, and project photos are re-encoded to at most
2400 px, so 1 GB holds roughly 300–500 receipts.

## Topology (render.yaml)

| Resource | Type / plan | Command | Notes |
|---|---|---|---|
| `room-by-room-web` | Web service, `0.5c-512mb`, Python, Frankfurt, `autoDeployTrigger: off` | build: `pip install -r requirements.txt && python manage.py collectstatic --noinput`; pre-deploy: `python manage.py migrate --noinput`; start: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120` | Health check `/healthz/` checks the database and exposes no user data. WhiteNoise serves hashed static files. |
| `room-by-room-receipts` | Background worker, `0.5c-512mb`, Frankfurt, `autoDeployTrigger: off` | `python manage.py process_receipts --watch --interval 3` | `maxShutdownDelaySeconds: 90`. On SIGTERM it finishes the job in hand (provider timeout 60 s), claims nothing new and exits. |
| `room-by-room-db` | Render Postgres `0.1c-256mb`, PostgreSQL **16**, Frankfurt | — | `diskSizeGB: 1` and `storageAutoscalingEnabled: false`. `ipAllowList: []` means no public access; services connect over the private network. Holds data and private files. |

**Auto-deploy is off.** Each deploy is a deliberate "Manual Deploy" of a reviewed commit.

## Blueprint validation

- **Offline (done):** `tests/test_render_blueprint.py` parses `render.yaml` with PyYAML. It checks:
  - every value the CTO approved;
  - plan and enum membership against Render's API enums;
  - that there is no `projects:` key;
  - that no secret values are present, and `ANTHROPIC_API_KEY` is absent.

  Run it with `pytest tests/test_render_blueprint.py`.
- **Official (not possible here):** `render blueprints validate render.yaml`, using the Render CLI built from
  source, needs a workspace and a login:
  - Result here: `Error: no workspace specified and no default workspace set`.
  - With `-w`: `Error: failed to create client: run 'render login' to authenticate`.
  - The check runs on Render's servers (`api.render.com`, which is also blocked from this sandbox).

  **Run it before applying**, from a machine logged into the founder's workspace:

  ```bash
  render login
  render workspace set
  render blueprints validate render.yaml
  ```

  It also checks conflicts with existing resources and the plans available to the workspace. It does not
  create anything.

## Attaching to the existing "Room by Room" project (no duplicate project)

The Blueprint deliberately has **no `projects:` key**. Declaring one could create a second project with the
same name. Instead:

1. Create the Blueprint from the workspace's Blueprints page, then review and apply it.
2. Open the existing **"Room by Room"** project. Use **Move** (bulk-select in the service list, or each
   resource's ••• menu → Move) to move `room-by-room-web`, `room-by-room-receipts`, `room-by-room-db` and the
   `room-by-room-shared` env group into its environment (for example "Production").
3. Confirm that the workspace still shows exactly one "Room by Room" project.

## Environment variables (names only)

The shared group `room-by-room-shared` is declared in the Blueprint:

- `PYTHON_VERSION` (3.13.14)
- `DJANGO_SECRET_KEY` (generated by Render)
- `DJANGO_DEBUG=0`, `DJANGO_HTTPS=1`, `DJANGO_SECURE_COOKIES=1`
- `PRIVATE_STORAGE_BACKEND=database`
- `STATIC_MANIFEST=1`
- `RECEIPT_EXTRACTOR=anthropic`
- `RECEIPT_MODEL=claude-haiku-4-5-20251001`

Each service gets `DATABASE_URL` from the database's internal connection string. Render provides
`RENDER_EXTERNAL_HOSTNAME`, which the settings add to the allowed hosts and trusted origins, so the initial
`onrender.com` address works.

**`ANTHROPIC_API_KEY` is not in the Blueprint.** Only when live reading is authorised, the founder enters it
privately in the dashboard:

1. Go to Env Groups → `room-by-room-shared` → Add variable, then save.
2. Both services inherit it from the group. Redeploy (or restart) both so they pick it up.

Never put it in Git, a report, a chat or a log. Without it, the app runs normally:

- the review page says "Automatic extraction not configured" and offers manual entry;
- any queued reading fails with that reason.

Automated tests cover this (`test_reading_requires_configuration_but_manual_review_still_works`).

## Access

- Every page except sign-in, `/healthz/` and the web manifest requires sign-in. There is no signup and no
  Django admin.
- HTTPS is enforced (`DJANGO_HTTPS=1`: SSL redirect, HSTS, secure cookies). `/healthz/` is exempt from the
  redirect.
- Create the owner account after the first deploy, from the web service Shell:
  `python manage.py create_owner alistair`. It prompts for the password and the account starts empty.
- Do not run `seed_demo` in production.

## Worker restart and shutdown behaviour

- The watch loop processes **one job per iteration** and checks the stop flag before every claim.
- On SIGTERM (deploys, restarts, maintenance) the job in hand finishes, nothing new is claimed and the worker
  exits without sleeping. Render waits up to 90 s, then sends SIGKILL.
- **Crash or SIGKILL mid-reading:** the job keeps its 180 s lease. After expiry it is re-claimed (attempt 2
  of 2), or failed if no attempts remain. Claim tokens stop a stale attempt from overwriting a newer one.
- Rehearsed locally with real processes, PostgreSQL 16 and the fake extractor
  (`docs/sprints/evidence/sprint-2a-closeout-worker-rehearsal.txt`):
  - **SIGTERM** with two queued jobs: job 1 finished and the worker exited 4.5 s later. Job 2 stayed queued.
  - **SIGKILL**: the lease was held, then recovered on attempt 2.
- **Hosted supervisor behaviour is unverified until deployment.**

## Backups and restore

- Paid Render Postgres provides point-in-time recovery (3 days on a Hobby workspace) and logical exports
  kept for 7 days. Because files live in the database, these cover receipts and photos too.
- Recommended weekly: download the dashboard export to the founder's encrypted storage.

### Restore rehearsal: no extra paid Render resources

Restore a Render export into an **isolated local PostgreSQL 16**, never into a new Render database:

1. Download the latest export from the dashboard (Database → Recovery → Export). Keep it only on encrypted
   storage. Check the format when downloaded: a custom-format dump uses `pg_restore` as below; a plain SQL
   file uses `psql -f`.
2. Restore into the local database:

   ```bash
   createdb rbr_restore
   pg_restore --no-owner --no-acl --exit-on-error -d rbr_restore <export>
   ```

3. Fingerprint the live data. Run this read-only command from the web service Shell:

   ```bash
   python manage.py restore_fingerprint > before.json
   ```

   Then fingerprint the restored copy, using the same app version (an older export may first need
   `python manage.py migrate --check`):

   ```bash
   DATABASE_URL=postgres://localhost/rbr_restore PRIVATE_STORAGE_BACKEND=database DJANGO_DEBUG=1 \
     python manage.py restore_fingerprint > after.json
   ```

4. `diff before.json after.json`. The two files must match on:
   - file count and the SHA-256 digest over all file bytes;
   - zero missing references and zero receipt checksum mismatches;
   - every owner's overall total and every project's net cost;
   - row counts. Writes between export and fingerprint explain small differences, so take the "before"
     fingerprint at the same time as the export.
5. Sign in locally against the restored copy, open a receipt and a photo, then delete the local database and
   the export file.

Rehearsed in this sprint on local PostgreSQL 16.14, with `pg_dump -Fc` standing in for the Render export:

- the fingerprints were identical (3 files, digest `074d248a…`, total £995.10, 3 confirmed purchases);
- through the restored database, the owner downloaded a receipt (SHA-256 matched the upload checksum) and a
  photo;
- other owners got 404 and anonymous users were redirected.

Evidence: `docs/sprints/evidence/sprint-2a-closeout-restore-fingerprint.json`. **A restore of a real Render
export has not been done (no infrastructure yet).**

## Monthly cost (USD, before tax): assumed Hobby workspace

| Item | Cost |
|---|---|
| Workspace (assumed **Hobby**, $0; verify before creation; **do not change the workspace plan**) | $0 |
| Web service `0.5c-512mb` | $7 |
| Background worker `0.5c-512mb` | $7 |
| Postgres `0.1c-256mb` | $6 |
| Postgres storage, 1 GB at $0.30/GB | $0.30 |
| **Baseline** | **≈ US$20.30 / month** |
| Extra, not in the baseline | tax; bandwidth or build minutes beyond the included allowance; Anthropic API calls |
| Anthropic API (Haiku 4.5, pay per use) | **not measured**. To be established from the token usage recorded on each job during the live test |

Before creation:

- Confirm the workspace tier on the dashboard. A different tier changes the cost and the PITR window.
- Confirm that the Blueprint's dashboard quotation matches about $20.30. Stop and report if it does not.

### Storage capacity

- Storage autoscaling is **off**. 1 GB is the starting size, and it can only grow (to 5 GB, then multiples
  of 5).
- Monthly, and before each batch of uploads, check database storage use (Database → Metrics, or
  `SELECT pg_size_pretty(pg_database_size('roombyroom'));`).
- **Before use reaches 80% (0.8 GB)**, raise a cost change: for example, 5 GB at about $1.50/month. Growth
  needs an **approved cost change**; nothing grows automatically.

Free tiers are unsuitable: they have no background workers, web services sleep, and Postgres expires after
30 days.

## Exact deployment steps (once the founder approves)

1. On the dashboard, confirm the workspace tier (do not change it) and that the existing "Room by Room"
   project is present.
2. From a logged-in machine, run `render blueprints validate render.yaml` (see above). Fix any finding
   before continuing.
3. Go to Blueprints → New Blueprint Instance → this repository, branch `sprint-2a` (or the approved branch),
   path `render.yaml`. Review:
   - the three resources and the env group;
   - plans `0.5c-512mb` / `0.5c-512mb` / `0.1c-256mb`;
   - PostgreSQL 16, 1 GB, autoscaling off, Frankfurt;
   - the **quotation of about $20.30/month**.

   Apply only if everything matches.
4. Move the resources and env group into the existing "Room by Room" project, as described above.
5. Wait for the first build and deploy. `preDeployCommand` runs migrations. Check that `/healthz/` returns
   `{"status":"ok"}` on the `onrender.com` address.
6. In the web service Shell, run `python manage.py create_owner alistair`.
7. Without an API key, sign in on the iPhone, upload a receipt and enter it manually. The review page should
   say extraction is not configured.
8. When live reading is authorised:
   1. Add `ANTHROPIC_API_KEY` privately to `room-by-room-shared` and redeploy both services.
   2. Read one real receipt. Check the worker log and the token usage on the job.
   3. Review it, allocate it and confirm it. Record the evidence, without receipt content, in the sprint
      report.
9. Take a dashboard export and run the local restore rehearsal above.

## Missing inputs

- Founder approval to create resources and spend about $20.30/month, plus a live-test API budget.
- Render dashboard access for the founder, or Render access for an authorised session, to run the official
  validator, apply the Blueprint and move resources into the project.
- A founder-authorised `ANTHROPIC_API_KEY`, entered privately by the founder.
- Network access to `render.com` from the build environment, to re-verify prices directly. Without it, the
  founder checks the dashboard quotation.
