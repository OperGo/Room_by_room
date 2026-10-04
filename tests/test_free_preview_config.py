"""Sprint 2B: the founder-applied free-preview checklist stays consistent with the code it deploys."""

import re
from pathlib import Path

import pytest

from apps.receipts.extraction import extraction_status, get_extractor
from config.settings import database_from_url

ROOT = Path(__file__).resolve().parent.parent
DOC = (ROOT / "docs" / "deployment-render-free-preview.md").read_text()
BUILD = "pip install -r requirements.txt && python manage.py collectstatic --noinput"
START = "python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 1 --timeout 120"


def test_checklist_has_the_exact_commands_and_settings():
    assert BUILD in DOC and START in DOC
    assert "**Branch:** `sprint-2a`" in DOC and "**Auto-Deploy:** **Off**" in DOC and "`/healthz/`" in DOC
    for key, value in {"PYTHON_VERSION": "3.13.14", "DJANGO_DEBUG": "0", "PRIVATE_STORAGE_BACKEND": "database",
                       "STATIC_MANIFEST": "1", "DJANGO_HTTPS": "1", "DJANGO_SECURE_COOKIES": "1",
                       "RECEIPT_EXTRACTOR": "anthropic", "RECEIPT_MODEL": "claude-haiku-4-5-20251001"}.items():
        assert f"| `{key}` | `{value}` |" in DOC, key
    assert "Leave `ANTHROPIC_API_KEY` unset" in DOC
    assert not re.search(r"sk-ant-|postgres(ql)?://[^\s:/]+:[^\s@]+@[a-z0-9-]+\.", DOC)  # no credentials


def test_guide_never_leaks_settings_or_passwords():
    # Sprint 2B closeout: no exported remote settings, no password-bearing URL in arguments, no open world.
    assert not re.search(r"^\s*export\b", DOC, re.M)
    assert "$DATABASE_URL" not in DOC and "read -rs" not in DOC
    assert "0.0.0.0/0" in DOC and "Never use `0.0.0.0/0`" in DOC
    for command in ("python scripts/render_db.py create-owner alistair",
                    "python scripts/render_db.py backup --out", "python scripts/render_db.py restore-check"):
        assert command in DOC
    assert "Web service → Connect → Outbound" in DOC and "Keep these rules permanently" in DOC
    assert "Never add `DJANGO_ALLOW_INSECURE_KEY` to the service" in DOC


def test_deployable_code_is_present():
    requirements = (ROOT / "requirements.txt").read_text().lower()
    assert "gunicorn==" in requirements and "whitenoise==" in requirements
    from apps.core.storage import DatabaseStorage  # noqa: F401
    from config.wsgi import application

    assert callable(application)  # `gunicorn config.wsgi` serves this module's `application`


def test_url_query_parameters_are_not_forwarded_so_pgsslmode_is_needed():
    config = database_from_url("postgres://u:p@db.example.com:5432/name?sslmode=require")
    assert config["NAME"] == "name" and "OPTIONS" not in config  # hence PGSSLMODE=require in the checklist


@pytest.mark.django_db
def test_missing_key_keeps_manual_route(settings):
    settings.RECEIPT_EXTRACTOR = "anthropic"
    settings.ANTHROPIC_API_KEY = ""
    available, message, _ = extraction_status()
    assert get_extractor() is None and available is False
    assert message.startswith("Automatic extraction not configured")


def test_pilot_checklist_matches_the_worker_and_settings():
    pilot = (ROOT / "docs" / "receipt-pilot.md").read_text()
    for text in ("| Build command | `pip install -r requirements.txt` |",
                 "| Start command | `python manage.py process_receipts --watch --interval 3` |",
                 "**Starter** (0.5c-512mb), **1 instance**", "| Auto-Deploy | **Off** |", "**90 seconds**",
                 "| Region | **Frankfurt**", "| `RECEIPT_MODEL` | `claude-haiku-4-5-20251001` |",
                 "| `PRIVATE_STORAGE_BACKEND` | `database` |", "| `ANTHROPIC_API_KEY` | **Leave out for now.**",
                 "**Do not** copy the web secret", "python manage.py receipt_jobs", "Claimable at start: 0 job(s)",
                 "auto-reload / automatic top-up is OFF", "spend limit to **US$5**"):
        assert text in pilot, text
    assert not re.search(r"sk-ant-|postgres(ql)?://[^\s:/]+:[^\s@]+@", pilot)  # no credentials
    # The worker settings named in the guide exist; the attempt limit is fixed in code.
    from django.conf import settings

    assert settings.RECEIPT_MAX_ATTEMPTS == 2 and settings.RECEIPT_IMAGE_LONG_EDGE == 1568
    blueprint = (ROOT / "render.yaml").read_text()
    assert "NEW-INSTALL ONLY" in blueprint


def test_runtime_decision_checklist_matches_the_code():
    doc = (ROOT / "docs" / "receipt-runtime-decision.md").read_text()
    for text in ("Command `python manage.py process_receipts --once`", "Build command `pip install -r requirements.txt`",
                 "Schedule `* * * * *`", "Region **Frankfurt**", "Instance type **Starter**", "Auto-Deploy **Off**",
                 "| `RECEIPT_MODEL` | `claude-haiku-4-5-20251001` |", "| `PRIVATE_STORAGE_BACKEND` | `database` |",
                 "**Do not add the key yet.**", "Claimable at start: 0 job(s)", "keep **PostgreSQL 18**",
                 "monthly spend limit to US$5", "auto-reload is off", "US$0.00016 per minute",
                 "about US$7.50–9.80 per month", '"Save only" does not apply it to the next', "final tested SHA",
                 "python manage.py receipt_jobs --limit 20", "wait until no run is active",
                 "Monitoring threshold, not a billing cap", "Keeps billing even if the cron trial stops",
                 "Total API testing allowance", "roughly 1–2 minutes"):
        assert text in doc, text
    assert not re.search(r"sk-ant-|postgres(ql)?://[^\s:/]+:[^\s@]+@", doc)
    from django.core.management import get_commands

    assert "process_receipts" in get_commands() and "receipt_jobs" in get_commands()
