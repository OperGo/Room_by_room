"""Real concurrency tests. They need PostgreSQL row locks and are skipped on SQLite.

Run with: DATABASE_URL=postgres://... pytest tests/test_concurrency_pg.py
"""

import datetime
import threading
import time
import uuid
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection, connections

from apps.core.exceptions import BusinessRuleError
from apps.costs import services
from apps.costs.models import OpeningCostBalance, Purchase
from apps.projects.models import Project
from apps.receipts.models import ReceiptDocument, ReceiptDraft

from .conftest import line, purchase_input, to

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(connection.vendor != "postgresql", reason="requires PostgreSQL"),
]

D = Decimal
real_validate = services.validate_purchase_input


def slow_validate(*args, **kwargs):
    time.sleep(0.3)  # widen the race window
    return real_validate(*args, **kwargs)


def run_concurrently(fn, n=2):
    barrier = threading.Barrier(n)
    results, errors = [], []

    def worker():
        try:
            barrier.wait()
            results.append(fn())
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    return results, errors


@pytest.fixture
def setup(django_user_model):
    owner = django_user_model.objects.create_user(username="pg-owner", password="x-very-long-pass")
    office = Project.objects.create(owner=owner, title="Office")
    return owner, office


def test_double_confirm_of_one_draft_posts_once(setup):
    owner, office = setup
    document = ReceiptDocument.objects.create(owner=owner, storage_key="k", checksum="c", mime="image/jpeg", size=1)
    draft = ReceiptDraft.objects.create(owner=owner, document=document)
    data = purchase_input([line("MDF", "32.00", [to(office, "32.00")])])
    with mock.patch("apps.costs.services.validate_purchase_input", side_effect=slow_validate):
        results, errors = run_concurrently(lambda: services.post_purchase(owner, data, source_draft=draft, draft_version=draft.version))
    assert not errors
    assert len({p.pk for p in results}) == 1
    assert Purchase.objects.count() == 1


def test_duplicate_submission_key_posts_once(setup):
    owner, office = setup
    key = uuid.uuid4()
    data = purchase_input([line("MDF", "32.00", [to(office, "32.00")])])
    with mock.patch("apps.costs.services.validate_purchase_input", side_effect=slow_validate):
        results, errors = run_concurrently(lambda: services.post_purchase(owner, data, submission_key=key))
    assert not errors, errors
    assert len({p.pk for p in results}) == 1
    assert Purchase.objects.count() == 1


def test_concurrent_balance_replacement_never_goes_negative(setup):
    owner, office = setup
    balance = services.create_opening_balance(owner, office, amount=D("500.00"), coverage_through=datetime.date(2026, 8, 31))
    data = purchase_input([line("Old", "300.00", [to(office, "300.00")])], date=datetime.date(2026, 8, 1))
    choice = [services.BalanceChoice(str(balance.uuid), "replace", D("300.00"))]
    with mock.patch("apps.costs.services.validate_purchase_input", side_effect=slow_validate):
        results, errors = run_concurrently(lambda: services.post_purchase(owner, data, balance_choices=choice))
    assert len(results) == 1 and len(errors) == 1 and isinstance(errors[0], BusinessRuleError)
    balance.refresh_from_db()
    assert balance.amount == D("200.00")
    assert Purchase.objects.count() == 1


def test_concurrent_refunds_respect_cap(setup):
    owner, office = setup
    purchase = services.post_purchase(owner, purchase_input([line("Filler", "9.50", [to(office, "9.50")])]))

    def refund():
        time.sleep(0.05)
        return services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 13),
                                        amounts={f"project:{office.uuid}": D("9.50")})

    results, errors = run_concurrently(refund)
    assert len(results) == 1 and len(errors) == 1
    assert Purchase.objects.filter(kind="refund").count() == 1


def test_rollback_on_failure_leaves_no_rows(setup):
    owner, office = setup
    data = purchase_input([line("MDF", "32.00", [to(office, "32.00")])])
    with mock.patch("apps.costs.services._apply_balance_choices", side_effect=RuntimeError("crash")):
        with pytest.raises(RuntimeError):
            services.post_purchase(owner, data)
    assert Purchase.objects.count() == 0
    assert OpeningCostBalance.objects.count() == 0


# ------------------------------------------------------------------ Sprint 2: reading jobs


@pytest.fixture
def reading_draft(setup, settings):
    settings.RECEIPT_EXTRACTOR = "fake"
    owner, _ = setup
    document = ReceiptDocument.objects.create(owner=owner, storage_key="k", checksum="c2", mime="image/jpeg", size=1)
    return owner, ReceiptDraft.objects.create(owner=owner, document=document)


def test_competing_claims_get_one_job_each(reading_draft):
    from apps.receipts import jobs
    from apps.receipts.models import ExtractionJob

    owner, draft = reading_draft
    jobs.request_reading(owner, draft, 1)
    results, errors = run_concurrently(lambda: jobs.claim_next_job(), n=4)
    assert not errors
    claimed = [r for r in results if r is not None]
    assert len(claimed) == 1
    job = ExtractionJob.objects.get()
    assert job.attempts == 1 and job.status == "processing"


def test_concurrent_read_requests_create_one_active_job(reading_draft):
    from apps.receipts import jobs
    from apps.receipts.models import ExtractionJob

    owner, draft = reading_draft
    results, errors = run_concurrently(lambda: jobs.request_reading(owner, draft, 1), n=3)
    assert not errors, errors
    assert len({j.pk for j in results}) == 1
    assert ExtractionJob.objects.count() == 1


def test_job_finish_racing_owner_save_never_overwrites_edits(reading_draft):
    from apps.receipts import jobs
    from apps.receipts.extraction import SAMPLE_RESULT
    from apps.receipts.normalise import normalise
    from apps.receipts.services import save_draft

    owner, draft = reading_draft
    jobs.request_reading(owner, draft, 1)
    job, token = jobs.claim_next_job()
    data = normalise(SAMPLE_RESULT)
    outcomes = {}

    def finish():
        outcomes["job"] = jobs.finish_success(job.pk, token, data, "m")

    def save():
        try:
            outcomes["save"] = save_draft(owner, draft, 1, {"merchant": "Typed by owner", "lines": []})
        except Exception as exc:  # noqa: BLE001
            outcomes["save"] = exc

    barrier = threading.Barrier(2)

    def run(fn):
        try:
            barrier.wait()
            fn()
        finally:
            connections.close_all()

    threads = [threading.Thread(target=run, args=(fn,)) for fn in (finish, save)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    draft.refresh_from_db()
    job.refresh_from_db()
    if job.result_state == "applied":
        # The reading won; the owner's stale save was refused rather than silently mixed.
        assert isinstance(outcomes["save"], Exception) and draft.data["merchant"] == "Sample Hardware Co"
    else:
        assert job.result_state == "held" and draft.data["merchant"] == "Typed by owner"
    assert Purchase.objects.count() == 0
