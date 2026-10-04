"""Reading jobs end to end with the fake adapter. No job or extraction creates cost."""

import copy
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError, StaleObjectError
from apps.costs.models import Purchase
from apps.costs.selectors import overall_summary, project_cost_summary
from apps.receipts import jobs
from apps.receipts.extraction import SAMPLE_RESULT, ExtractionError, FakeExtractor
from apps.receipts.models import ExtractionJob, ReceiptDraft

from .conftest import image_bytes, upload

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fake_extractor(settings):
    settings.RECEIPT_EXTRACTOR = "fake"
    settings.RECEIPT_RETRY_DELAY_SECONDS = 30
    settings.RECEIPT_LEASE_SECONDS = 180


@pytest.fixture
def draft(client_owner, owner):
    client_owner.post(reverse("receipts:new"), {"receipt": upload("r.jpg", image_bytes())})
    return ReceiptDraft.objects.get(owner=owner)


def later(seconds):
    return timezone.now() + datetime.timedelta(seconds=seconds)


def assert_no_cost(owner):
    assert Purchase.objects.count() == 0
    assert overall_summary(owner).total == Decimal("0.00")


def test_full_workflow_read_review_allocate_confirm_once(client_owner, owner, office, hallway, draft):
    page = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert "Read receipt automatically" in page and "test extractor" in page.lower()
    client_owner.post(reverse("receipts:read", args=[draft.uuid]), {"version": draft.version})
    client_owner.post(reverse("receipts:read", args=[draft.uuid]), {"version": draft.version})  # double tap
    assert ExtractionJob.objects.count() == 1
    assert_no_cost(owner)
    status = client_owner.get(reverse("receipts:reading_status", args=[draft.uuid])).json()
    assert status["status"] == "queued" and "merchant" not in status
    call_command("process_receipts", "--once")
    draft.refresh_from_db()
    job = ExtractionJob.objects.get()
    assert job.status == "succeeded" and job.result_state == "applied" and job.attempts == 1
    assert draft.version == 2 and draft.data["merchant"] == "Sample Hardware Co"
    assert_no_cost(owner)
    page = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert "Synthetic test reading" in page and 'value="Sample Hardware Co"' in page and "Check this line" in page
    assert "Items match the receipt total" in page
    # The owner allocates (the model never chose projects) and splits one line.
    lines = draft.data["lines"]
    post = {"version": draft.version, "merchant": "Sample Hardware Co", "transaction_date": "2026-09-26", "total": "31.17"}
    for i, line in enumerate(lines):
        post.update({f"line-{i}-description": line["description"], f"line-{i}-amount": line["amount"],
                     f"line-{i}-line_type": line["line_type"], f"line-{i}-category": line["category"],
                     f"line-{i}-quantity": line["quantity"], f"line-{i}-alloc-0-dest": f"project:{office.uuid}"})
    post["line-2-alloc-0-amount"] = "5.00"
    post["line-2-alloc-1-dest"] = f"project:{hallway.uuid}"
    post["line-2-alloc-1-amount"] = "3.50"
    post["line-4-alloc-0-dest"] = "shared_tools"
    first = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), post)
    second = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), post)
    assert first.status_code == second.status_code == 302 and first["Location"] == second["Location"]
    assert Purchase.objects.count() == 1
    assert project_cost_summary(office).net == Decimal("23.72")  # 6.49 + 7.98 + 5.00 + 4.25
    assert project_cost_summary(hallway).net == Decimal("3.50")
    assert overall_summary(owner).total == Decimal("31.17")
    assert overall_summary(owner).shared_tools == Decimal("3.95")


def test_reading_requires_configuration_but_manual_review_still_works(client_owner, owner, office, draft, settings):
    settings.RECEIPT_EXTRACTOR = "anthropic"
    settings.ANTHROPIC_API_KEY = ""
    response = client_owner.post(reverse("receipts:read", args=[draft.uuid]), {"version": draft.version}, follow=True)
    assert b"Automatic extraction not configured" in response.content
    assert not ExtractionJob.objects.exists()
    post = {"version": draft.version, "merchant": "Shop", "transaction_date": "2026-09-26", "total": "5.00",
            "line-0-description": "Glue", "line-0-amount": "5.00", "line-0-alloc-0-dest": f"project:{office.uuid}"}
    assert client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), post).status_code == 302
    assert project_cost_summary(office).net == Decimal("5.00")


def test_worker_marks_jobs_failed_if_configuration_disappears(owner, draft, settings):
    jobs.request_reading(owner, draft, draft.version)
    settings.RECEIPT_EXTRACTOR = "anthropic"
    settings.ANTHROPIC_API_KEY = ""
    jobs.process_available()
    job = ExtractionJob.objects.get()
    assert job.status == "failed" and job.error_code == "not_configured"
    assert_no_cost(owner)


def test_timeout_retries_once_then_fails_without_storm(owner, draft):
    FakeExtractor.queue.extend([ExtractionError("timeout", "Reading timed out.", retryable=True)] * 3)
    jobs.request_reading(owner, draft, draft.version)
    assert jobs.process_available() == 1
    job = ExtractionJob.objects.get()
    assert job.status == "queued" and job.attempts == 1 and job.available_at > timezone.now()
    assert jobs.process_available() == 0  # backoff respected: no immediate retry storm
    assert jobs.process_available(now=later(31)) == 1
    job.refresh_from_db()
    assert job.status == "failed" and job.attempts == 2 and job.error_code == "timeout"
    assert jobs.process_available(now=later(3600)) == 0
    assert len(FakeExtractor.calls) == 2
    draft.refresh_from_db()
    assert draft.version == 1 and draft.data == {}
    assert_no_cost(owner)


def test_retryable_failure_then_success(owner, draft):
    FakeExtractor.queue.append(ExtractionError("rate_limited", "Busy.", retryable=True))
    jobs.request_reading(owner, draft, draft.version)
    jobs.process_available()
    jobs.process_available(now=later(31))
    job = ExtractionJob.objects.get()
    assert job.status == "succeeded" and job.attempts == 2 and job.result_state == "applied"


@pytest.mark.parametrize("outcome,code", [
    (ExtractionError("malformed", "Unreadable result."), "malformed"),
    (ExtractionError("refused", "Declined."), "refused"),
    ({"merchant": "x"}, "malformed"),  # schema-violating output caught by the normaliser
    (RuntimeError("boom with receipt text"), "internal"),
])
def test_permanent_failures_preserve_manual_route(client_owner, owner, draft, outcome, code):
    FakeExtractor.queue.append(outcome)
    jobs.request_reading(owner, draft, draft.version)
    jobs.process_available()
    job = ExtractionJob.objects.get()
    assert job.status == "failed" and job.attempts == 1 and job.error_code == code
    assert "receipt text" not in job.error
    page = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert "Couldn’t read this receipt" in page and "Try reading again" in page and "Confirm purchase" in page
    assert_no_cost(owner)


def test_unreconciled_and_foreign_results_are_flagged_and_create_no_cost(client_owner, owner, office, draft):
    foreign = copy.deepcopy(SAMPLE_RESULT)
    foreign["currency"] = "EUR"
    FakeExtractor.queue.append(foreign)
    jobs.request_reading(owner, draft, draft.version)
    jobs.process_available()
    draft.refresh_from_db()
    assert draft.data["total"] == "" and draft.data["extraction"]["gbp_confirmation_required"]
    page = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert "EUR 31.17" in page and "All amounts above are in pounds sterling" in page
    post = {"version": draft.version, "merchant": "Paris shop", "transaction_date": "2026-09-26", "total": "27.00",
            "line-0-description": "Tools", "line-0-amount": "27.00", "line-0-alloc-0-dest": f"project:{office.uuid}"}
    refused = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), post)
    assert b"Confirm that every amount you entered is in pounds sterling" in refused.content
    assert_no_cost(owner)
    ok = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), {**post, "gbp_confirmed": "1"})
    assert ok.status_code == 302 and project_cost_summary(office).net == Decimal("27.00")


def test_edits_during_reading_are_never_overwritten(client_owner, owner, draft):
    jobs.request_reading(owner, draft, draft.version)
    client_owner.post(reverse("receipts:save", args=[draft.uuid]),
                      {"version": "1", "merchant": "Typed by owner", "transaction_date": "2026-09-26"})
    jobs.process_available()
    draft.refresh_from_db()
    job = ExtractionJob.objects.get()
    assert job.result_state == "held" and draft.data["merchant"] == "Typed by owner" and draft.version == 2
    page = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert "A reading finished after you changed this draft" in page
    with pytest.raises(StaleObjectError):
        jobs.apply_held_result(owner, job, 1)
    client_owner.post(reverse("receipts:apply_reading", args=[draft.uuid]), {"version": "2", "job": str(job.pk)})
    draft.refresh_from_db()
    job.refresh_from_db()
    assert draft.data["merchant"] == "Sample Hardware Co" and draft.version == 3 and job.result_state == "applied"
    assert_no_cost(owner)


def test_handled_draft_is_never_changed_by_a_late_job(client_owner, owner, office, draft):
    jobs.request_reading(owner, draft, draft.version)
    post = {"version": "1", "merchant": "Manual", "transaction_date": "2026-09-26", "total": "5.00",
            "line-0-description": "Glue", "line-0-amount": "5.00", "line-0-alloc-0-dest": f"project:{office.uuid}"}
    client_owner.post(reverse("receipts:confirm", args=[draft.uuid]), post)
    jobs.process_available()
    draft.refresh_from_db()
    job = ExtractionJob.objects.get()
    assert job.result_state == "discarded" and draft.data == {} and draft.review_status == "confirmed"
    assert overall_summary(owner).total == Decimal("5.00")


def test_request_rules(owner, draft):
    with pytest.raises(StaleObjectError):
        jobs.request_reading(owner, draft, 5)
    with pytest.raises(StaleObjectError):
        jobs.request_reading(owner, draft, "abc")
    first = jobs.request_reading(owner, draft, 1)
    assert jobs.request_reading(owner, draft, 1).pk == first.pk  # one active job per document
    from apps.receipts.services import discard_draft

    jobs.process_available()
    draft.refresh_from_db()
    discard_draft(owner, draft, draft.version)
    with pytest.raises(BusinessRuleError):
        jobs.request_reading(owner, draft, draft.version + 1)


def test_expired_lease_recovery_and_late_attempt_cannot_overwrite(owner, draft):
    jobs.request_reading(owner, draft, draft.version)
    job, first_token = jobs.claim_next_job()
    assert job.attempts == 1
    assert jobs.claim_next_job() is None  # leased
    job2, second_token = jobs.claim_next_job(now=later(181))  # lease expired: recovered
    assert job2.pk == job.pk and job2.attempts == 2 and second_token != first_token
    from apps.receipts.normalise import normalise

    data = normalise(SAMPLE_RESULT)
    assert jobs.finish_success(job.pk, first_token, data, "late") is None  # stale attempt ignored
    assert jobs.finish_failure(job.pk, first_token, ExtractionError("timeout", "x", True)) is None
    assert jobs.finish_success(job.pk, second_token, data, "fresh").model_version == "fresh"
    draft.refresh_from_db()
    assert draft.data["merchant"] == "Sample Hardware Co" and draft.version == 2


def test_expired_lease_with_no_attempts_left_fails(owner, draft):
    jobs.request_reading(owner, draft, draft.version)
    jobs.claim_next_job()
    jobs.claim_next_job(now=later(181))
    assert jobs.claim_next_job(now=later(400)) is None
    job = ExtractionJob.objects.get()
    assert job.status == "failed" and job.attempts == 2 and job.error_code == "timeout"
    assert_no_cost(owner)


def test_usage_metadata_is_recorded_and_shown(client_owner, owner, draft):
    from apps.receipts.extraction import ReceiptExtractionResult

    FakeExtractor.queue.append(lambda doc: ReceiptExtractionResult(
        raw=SAMPLE_RESULT, model_version="claude-haiku-4-5-20251001",
        usage={"input_tokens": 1600, "output_tokens": 420, "request_id": "req_1", "stop_reason": "end_turn"}))
    jobs.request_reading(owner, draft, draft.version)
    jobs.process_available()
    job = ExtractionJob.objects.get()
    assert job.usage["input_tokens"] == 1600 and job.usage["attempts"][0]["request_id"] == "req_1"
    page = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert "1600 input / 420 output tokens" in page


def test_polling_endpoint_is_owner_scoped_and_status_only(client, owner, intruder, draft):
    client.force_login(intruder)
    assert client.get(reverse("receipts:reading_status", args=[draft.uuid])).status_code == 404
    assert client.post(reverse("receipts:read", args=[draft.uuid]), {"version": "1"}).status_code == 404
    assert client.post(reverse("receipts:apply_reading", args=[draft.uuid]), {"version": "1", "job": "1"}).status_code == 404
    client.force_login(owner)
    body = client.get(reverse("receipts:reading_status", args=[draft.uuid])).json()
    assert body == {"status": "none", "draft_version": 1}


def test_worker_command_modes(owner, draft):
    jobs.request_reading(owner, draft, draft.version)
    call_command("process_receipts", "--once", "--max-jobs", "1")
    assert ExtractionJob.objects.get().status == "succeeded"
    with pytest.raises(Exception):
        call_command("process_receipts")  # a mode is required


# ------------------------------------------------------------------ Sprint 2A: malformed output containment


@pytest.mark.parametrize("patch", [
    {"uncertain_fields": [{}]}, {"warnings": 1},
    {"items": [{"description": "x", "quantity": None, "line_total": "1.00", "uncertain": False}, ["nested"]]},
])
def test_malformed_output_fails_cleanly_and_next_job_runs(client_owner, owner, draft, patch):
    from apps.receipts.extraction import ReceiptExtractionResult

    bad = copy.deepcopy(SAMPLE_RESULT)
    bad.update(patch)
    FakeExtractor.queue.append(lambda doc: ReceiptExtractionResult(
        raw=bad, model_version="m", usage={"input_tokens": 900, "output_tokens": 50}))
    jobs.request_reading(owner, draft, draft.version)
    # A second receipt queued behind the bad one, processed in the same worker run.
    client_owner.post(reverse("receipts:new"), {"receipt": upload("r2.jpg", image_bytes(color="red"))})
    second = ReceiptDraft.objects.exclude(pk=draft.pk).get()
    jobs.request_reading(owner, second, second.version)
    assert jobs.process_available() == 2
    first_job = ExtractionJob.objects.get(draft=draft)
    second_job = ExtractionJob.objects.get(draft=second)
    draft.refresh_from_db()
    if "items" in patch:
        # A nested malformed row is skipped: the reading is applied but marked incomplete.
        assert first_job.status == "succeeded" and draft.data["extraction"]["incomplete"] is True
        assert draft.data["extraction"]["reconciled"] is False
    else:
        assert first_job.status == "failed" and first_job.error_code == "malformed" and first_job.attempts == 1
        assert first_job.usage["input_tokens"] == 900  # usage retained
        assert draft.data == {} and draft.version == 1  # draft untouched
    assert second_job.status == "succeeded"
    assert_no_cost(owner)


def test_unexpected_crash_in_one_job_does_not_stop_the_worker(owner, draft, client_owner, monkeypatch):
    calls = {"n": 0}
    real = jobs.finish_success

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database hiccup")
        return real(*args, **kwargs)

    monkeypatch.setattr(jobs, "finish_success", flaky)
    jobs.request_reading(owner, draft, draft.version)
    client_owner.post(reverse("receipts:new"), {"receipt": upload("r2.jpg", image_bytes(color="red"))})
    second = ReceiptDraft.objects.exclude(pk=draft.pk).get()
    jobs.request_reading(owner, second, second.version)
    assert jobs.process_available() == 2
    assert ExtractionJob.objects.get(draft=draft).status == "failed"
    assert ExtractionJob.objects.get(draft=second).status == "succeeded"


def test_save_conflict_after_reading_keeps_every_submitted_value(client_owner, owner, office, hallway, draft):
    jobs.request_reading(owner, draft, draft.version)
    jobs.process_available()  # reading applied: stored draft is now version 2
    draft.refresh_from_db()
    assert draft.version == 2
    mine = {"version": "1", "merchant": "Typed by owner", "transaction_date": "2026-09-27", "total": "12.00",
            "line-0-description": "My glue", "line-0-amount": "12.00", "line-0-flag": "1",
            "line-0-alloc-0-dest": f"project:{office.uuid}", "line-0-alloc-0-amount": "7.00",
            "line-0-alloc-1-dest": f"project:{hallway.uuid}", "line-0-alloc-1-amount": "5.00"}
    conflict = client_owner.post(reverse("receipts:save", args=[draft.uuid]), mine)
    assert conflict.status_code == 409
    body = conflict.content.decode()
    assert "Not saved yet: this draft changed since you opened it" in body
    for value in ('value="Typed by owner"', 'value="My glue"', 'value="7.00"', 'value="5.00"', 'value="2026-09-27"',
                  "Check this line", 'name="version" value="2"', "data-dirty-on-load", "Save draft (keep my version)"):
        assert value in body, value
    draft.refresh_from_db()
    assert draft.version == 2 and draft.data["merchant"] == "Sample Hardware Co"  # nothing silently forced
    # Deliberate retry with the current version keeps the owner's version.
    saved = client_owner.post(reverse("receipts:save", args=[draft.uuid]), {**mine, "version": "2"})
    assert saved.status_code == 302
    draft.refresh_from_db()
    assert draft.version == 3 and draft.data["merchant"] == "Typed by owner"
    assert draft.data["lines"][0]["allocations"][1]["amount"] == "5.00"
    assert draft.data["extraction"]["job_id"]  # reading metadata kept with the owner's values
    assert draft.data["extraction"]["edited_by_owner"] is True and draft.data["extraction"]["reconciled"] is False
    page = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert 'value="Typed by owner"' in page and 'value="My glue"' in page
    assert "then edited by you" in page and "Items match the receipt total" not in page
    assert_no_cost(owner)


# ------------------------------------------------------------------ Sprint 2A closeout: worker shutdown


def _two_queued_jobs(client_owner, owner, draft):
    jobs.request_reading(owner, draft, draft.version)
    client_owner.post(reverse("receipts:new"), {"receipt": upload("r2.jpg", image_bytes(color="red"))})
    second = ReceiptDraft.objects.exclude(pk=draft.pk).get()
    jobs.request_reading(owner, second, second.version)
    return second


@pytest.fixture
def keep_test_connection(monkeypatch):
    # The real worker closes stale connections each iteration; inside a test transaction that would
    # close the test's own PostgreSQL connection, so it is stubbed here.
    from apps.receipts.management.commands import process_receipts as command

    monkeypatch.setattr(command, "close_old_connections", lambda: None)


@pytest.fixture
def restore_signals():
    import signal

    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    yield
    for sig, handler in saved.items():
        signal.signal(sig, handler)


def test_watch_sigterm_finishes_current_job_and_leaves_next_queued(client_owner, owner, draft, restore_signals,
                                                                     keep_test_connection, monkeypatch):
    import os
    import signal

    from apps.receipts.extraction import ReceiptExtractionResult

    second = _two_queued_jobs(client_owner, owner, draft)

    def sigterm_mid_job(doc):
        os.kill(os.getpid(), signal.SIGTERM)  # the platform asks the worker to stop during job one
        return ReceiptExtractionResult(raw=copy.deepcopy(SAMPLE_RESULT), model_version="m", usage={})

    FakeExtractor.queue.append(sigterm_mid_job)
    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    call_command("process_receipts", "--watch", "--interval", "30")
    first_job = ExtractionJob.objects.get(draft=draft)
    second_job = ExtractionJob.objects.get(draft=second)
    assert first_job.status == "succeeded" and first_job.result_state == "applied"
    assert second_job.status == "queued" and second_job.attempts == 0 and not second_job.claim_token
    assert slept == []  # never sleeps once stopping
    assert_no_cost(owner)
    # The next worker run picks the queued job up normally.
    assert jobs.process_available() == 1
    assert ExtractionJob.objects.get(draft=second).status == "succeeded"


def test_watch_processes_one_job_per_iteration_without_idle_sleep(client_owner, owner, draft, keep_test_connection,
                                                                  monkeypatch):
    second = _two_queued_jobs(client_owner, owner, draft)
    from apps.receipts.management.commands import process_receipts as command

    seen = []
    real = command.process_available

    def spy(max_jobs=None, now=None):
        seen.append(max_jobs)
        count = real(max_jobs=max_jobs, now=now)
        if not count:
            raise KeyboardInterrupt  # end the test loop at the first empty poll
        return count

    monkeypatch.setattr(command, "process_available", spy)
    with pytest.raises(KeyboardInterrupt):
        call_command("process_receipts", "--watch", "--interval", "30")
    assert seen == [1, 1, 1]
    assert {j.status for j in ExtractionJob.objects.filter(draft__in=[draft, second])} == {"succeeded"}


def test_idle_wait_wakes_promptly_when_stopped(monkeypatch):
    from apps.receipts.management.commands.process_receipts import Command

    stop = {"flag": False}
    slept = []

    def fake_sleep(seconds):
        slept.append(seconds)
        stop["flag"] = True  # SIGTERM arrives during the idle wait

    monkeypatch.setattr("time.sleep", fake_sleep)
    Command._idle(30, stop)
    assert slept == [0.2]  # short slices, so shutdown is never delayed by the full interval


# ------------------------------------------------------------------ Sprint 2A closeout: returned editors stay dirty


def _confirm_post(draft, office, **extra):
    return {"version": str(draft.version), "merchant": "Typed by owner", "transaction_date": "2026-09-27",
            "total": "12.00", "line-0-description": "My glue", "line-0-amount": "12.00",
            "line-0-line_type": "item", "line-0-category": "material",
            "line-0-alloc-0-dest": f"project:{office.uuid}", **extra}


def test_every_returned_editor_starts_dirty_and_get_stays_clean(client_owner, owner, office, draft):
    url = reverse("receipts:confirm", args=[draft.uuid])
    page = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert "data-dirty-on-load" not in page  # stored values: clean
    # 1. Validation failure (total does not match).
    invalid = client_owner.post(url, _confirm_post(draft, office, total="99.00"))
    # 2. Stale confirmation (old version).
    stale = client_owner.post(url, _confirm_post(draft, office, version="0"))
    assert stale.status_code == 409
    # 3. GBP acknowledgement missing.
    draft.data = {"extraction": {"gbp_confirmation_required": True}}
    draft.save(update_fields=["data"])
    gbp = client_owner.post(url, _confirm_post(draft, office))
    draft.data = {}
    draft.save(update_fields=["data"])
    # 4. Possible duplicate needing acknowledgement.
    from apps.costs import services as cost_services
    from apps.costs.forms import PurchaseEditor

    editor = PurchaseEditor(owner, _confirm_post(draft, office, transaction_date="2026-09-26"))
    assert editor.is_valid(), editor.errors
    cost_services.post_purchase(owner, editor.purchase_input)
    duplicate = client_owner.post(url, _confirm_post(draft, office))
    assert "This may duplicate a purchase" in duplicate.content.decode()
    # 5. Opening-balance overlap needing a choice.
    cost_services.create_opening_balance(owner, office, amount=Decimal("50.00"),
                                         coverage_through=datetime.date(2026, 9, 30))
    overlap = client_owner.post(url, _confirm_post(draft, office))
    assert "This may already be in an opening balance" in overlap.content.decode()
    assert invalid.status_code == 200 and 'id="editor-errors"' in invalid.content.decode()
    for response in (invalid, stale, gbp, duplicate, overlap):
        body = response.content.decode()
        assert "data-dirty-on-load" in body and 'value="Typed by owner"' in body
    assert "pounds sterling" in gbp.content.decode()
    assert Purchase.objects.filter(source_draft=draft).count() == 0  # nothing confirmed by any redisplay
    assert Purchase.objects.count() == 1  # only the deliberately seeded earlier purchase


# ------------------------------------------------------------------ Sprint 2C pilot: what a worker would send


def _receipt_jobs_output():
    import io

    out = io.StringIO()
    call_command("receipt_jobs", stdout=out)
    return out.getvalue()


def test_receipt_jobs_lists_only_what_a_worker_would_claim(client_owner, owner, draft):
    from apps.receipts.jobs import claimable_jobs

    assert "Claimable now (a running worker would send these to the provider): 0" in _receipt_jobs_output()
    queued = jobs.request_reading(owner, draft, draft.version)
    assert list(claimable_jobs()) == [queued]
    # A permanently failed job is never claimed again, so starting a worker cannot silently retry it.
    FakeExtractor.queue.append(ExtractionError("refusal", "declined"))
    jobs.process_available()
    queued.refresh_from_db()
    assert queued.status == "failed" and list(claimable_jobs()) == []
    output = _receipt_jobs_output()
    assert "Claimable now (a running worker would send these to the provider): 0" in output
    assert f"  {queued.pk} | {str(draft.uuid)[:8]} | failed |" in output


def test_receipt_jobs_reports_usage_and_cost_without_receipt_content(client_owner, owner, draft):
    from apps.receipts.extraction import ReceiptExtractionResult

    FakeExtractor.queue.append(lambda doc: ReceiptExtractionResult(
        raw=copy.deepcopy(SAMPLE_RESULT), model_version="claude-haiku-4-5-20251001",
        usage={"input_tokens": 2000, "output_tokens": 600}))
    jobs.request_reading(owner, draft, draft.version)
    jobs.process_available()
    output = _receipt_jobs_output()
    assert "claude-haiku-4-5-20251001 | 2000/600 |" in output
    assert "estimated list-price cost US$0.0050" in output  # 2000 x $1/M + 600 x $5/M
    draft.refresh_from_db()
    assert draft.data["merchant"] not in output  # no merchant, amounts or file names in the listing
    assert draft.document.original_filename not in output and "31.17" not in output


def test_worker_announces_claimable_jobs_at_start(client_owner, owner, draft):
    import io

    job = jobs.request_reading(owner, draft, draft.version)
    out = io.StringIO()
    call_command("process_receipts", "--once", stdout=out)
    assert f"Claimable at start: 1 job(s) (ids [{job.pk}])" in out.getvalue()


def test_worker_log_lines_are_flushed_immediately(owner, draft):
    import io

    class Pipe(io.StringIO):
        flushes = 0

        def flush(self):
            Pipe.flushes += 1
            super().flush()

    out = Pipe()
    call_command("process_receipts", "--once", stdout=out)
    assert "Claimable at start: 0 job(s)" in out.getvalue() and Pipe.flushes >= 2  # announced + processed lines


def test_waiting_message_fits_the_cron_schedule(client_owner, owner, draft):
    # Milestone 2: a once-a-minute cron (plus cold start) must not look like a broken worker.
    job = jobs.request_reading(owner, draft, draft.version)
    assert jobs.job_state(job, now=job.created_at + datetime.timedelta(seconds=150))["stale_queue"] is False
    assert jobs.job_state(job, now=job.created_at + datetime.timedelta(seconds=301))["stale_queue"] is True
    page = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert "Readings normally start within 1–2 minutes." in page and "may not be running" not in page
