"""The receipt worker waits for database migrations (web/cron deploy race).

With auto-deploy the cron job can start new code before the web service has run ``migrate``. Until the
schema matches the code the worker must not claim, change or send any job.
"""
import io
import os
import signal

import pytest
from django.core.management import call_command
from django.db import DatabaseError

from apps.receipts import jobs
from apps.receipts.extraction import FakeExtractor
from apps.receipts.management.commands import process_receipts
from apps.receipts.models import ExtractionJob, ReceiptDraft

from .conftest import image_bytes, upload

JOB_FIELDS = ("status", "attempts", "claim_token", "lease_expires_at", "available_at", "started_at", "finished_at",
              "result_state", "error_code")


@pytest.fixture(autouse=True)
def fake_extractor(settings):
    settings.RECEIPT_EXTRACTOR = "fake"


@pytest.fixture
def queued_job(owner):
    from apps.core.uploads import validate_receipt
    from apps.receipts.services import store_receipt

    _, draft = store_receipt(owner, validate_receipt(upload("r.jpg", image_bytes())), "r.jpg")
    jobs.request_reading(owner, draft, draft.version)
    return ExtractionJob.objects.get()


def run_once():
    out = io.StringIO()
    call_command("process_receipts", "--once", stdout=out, stderr=io.StringIO())
    return out.getvalue()


@pytest.mark.django_db(transaction=True)
def test_pending_migration_defers_without_any_change_then_resumes(queued_job):
    job_before = ExtractionJob.objects.filter(pk=queued_job.pk).values(*JOB_FIELDS).get()
    draft_before = ReceiptDraft.objects.values("data", "version").get()
    call_command("migrate", "receipts", "0002", verbosity=0)  # the web service has not migrated yet
    try:
        output = run_once()  # exits normally: the next scheduled run tries again
        assert "Deferred: database migrations not yet applied (receipts.0003_draft_context_project)" in output
        assert "Claimable at start" not in output and "Processed" not in output
        assert FakeExtractor.calls == []  # no provider call
        assert ExtractionJob.objects.filter(pk=queued_job.pk).values(*JOB_FIELDS).get() == job_before
        assert ReceiptDraft.objects.values("data", "version").get() == draft_before
    finally:
        call_command("migrate", verbosity=0)  # the web deploy finishes migrating
    output = run_once()  # a later scheduled run
    assert "Claimable at start: 1 job(s)" in output and "Processed 1 job(s)." in output
    job = ExtractionJob.objects.get(pk=queued_job.pk)
    assert job.status == "succeeded" and job.attempts == 1 and len(FakeExtractor.calls) == 1


@pytest.mark.django_db
def test_database_errors_while_checking_are_not_treated_as_pending(queued_job, monkeypatch):
    def broken(*args, **kwargs):
        raise DatabaseError("connection lost")

    monkeypatch.setattr(process_receipts.MigrationExecutor, "migration_plan", broken)
    with pytest.raises(DatabaseError):
        run_once()
    assert ExtractionJob.objects.get().status == "queued" and FakeExtractor.calls == []


@pytest.fixture
def restore_signals():
    saved = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    yield
    for s, handler in saved.items():
        signal.signal(s, handler)


@pytest.mark.django_db
def test_watch_waits_without_claiming_and_starts_once_migrated(queued_job, monkeypatch, restore_signals):
    checks = iter([["receipts.0003_draft_context_project"], ["receipts.0003_draft_context_project"], []])
    monkeypatch.setattr(process_receipts, "pending_migrations", lambda: next(checks))
    idles, claims = [], []

    def idle(interval, stop):
        idles.append(ExtractionJob.objects.get().status)  # still untouched while waiting

    def process(max_jobs=None):
        claims.append(len(idles))
        os.kill(os.getpid(), signal.SIGTERM)  # stop after the first post-migration poll
        return 0

    monkeypatch.setattr(process_receipts.Command, "_idle", staticmethod(idle))
    monkeypatch.setattr(process_receipts, "process_available", process)
    monkeypatch.setattr(process_receipts, "close_old_connections", lambda: None)
    out = io.StringIO()
    call_command("process_receipts", "--watch", "--interval", "1", stdout=out, stderr=io.StringIO())
    output = out.getvalue()
    assert claims == [2]  # the first poll came only after two waits while migrations were pending
    assert idles[:2] == ["queued", "queued"]  # nothing claimed or changed during those waits
    assert "Deferred: database migrations not yet applied" in output
    assert "Database migrations applied; starting." in output and "Stopped." in output
    assert FakeExtractor.calls == []


def test_no_pending_migrations_in_the_test_database(db):
    assert process_receipts.pending_migrations() == []
