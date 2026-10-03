"""Receipt reading jobs: request, claim, run, finish. No function here creates cost.

Concurrency rules (PostgreSQL row locks; SQLite has none):
- requesting reading locks the draft and records its version; one active job per document;
- claiming locks the job row with SKIP LOCKED, stamps a fresh claim token and lease, and
  commits before the provider is called (no lock is held during the network call);
- finishing re-locks the job and only accepts the result if the claim token still matches,
  so an attempt whose lease expired cannot overwrite a newer attempt;
- results are applied to the draft only if it is still open and at the requested version;
  otherwise they are held for explicit review (or discarded if the draft was handled).
"""

import datetime
import logging
import uuid

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError, StaleObjectError, parse_version

from .extraction import ExtractionError, get_extractor
from .models import ExtractionJob, ReceiptDraft
from .normalise import NormaliseError, normalise

logger = logging.getLogger(__name__)


def latest_job(draft):
    return draft.jobs.order_by("-created_at", "-id").first()


def request_reading(owner, draft, expected_version):
    """Queue reading for a draft (explicit user action). Returns the active job."""
    extractor = get_extractor()
    if extractor is None:
        raise BusinessRuleError("Automatic extraction not configured. Enter the details from the receipt.")
    try:
        with transaction.atomic():
            locked = ReceiptDraft.objects.select_for_update().select_related("document").get(pk=draft.pk, owner=owner)
            if not locked.is_open:
                raise BusinessRuleError("This receipt has already been handled.")
            if parse_version(expected_version) != locked.version:
                raise StaleObjectError()
            active = ExtractionJob.objects.filter(document=locked.document, status__in=["queued", "processing"]).first()
            if active:
                return active
            return ExtractionJob.objects.create(
                document=locked.document, draft=locked, requested_draft_version=locked.version,
                adapter=extractor.name, max_attempts=settings.RECEIPT_MAX_ATTEMPTS,
            )
    except IntegrityError:
        # A concurrent request created the active job first.
        active = ExtractionJob.objects.filter(document_id=draft.document_id, status__in=["queued", "processing"]).first()
        if active:
            return active
        raise


def claim_next_job(now=None):
    """Claim one job transactionally. Returns (job, token) or None. Recovers expired leases."""
    now = now or timezone.now()
    while True:
        with transaction.atomic():
            job = (
                ExtractionJob.objects.select_for_update(skip_locked=True)
                .filter(
                    Q(status=ExtractionJob.Status.QUEUED) & (Q(available_at__isnull=True) | Q(available_at__lte=now))
                    | Q(status=ExtractionJob.Status.PROCESSING, lease_expires_at__lt=now)
                )
                .order_by("created_at", "id")
                .first()
            )
            if job is None:
                return None
            if job.status == ExtractionJob.Status.PROCESSING and job.attempts >= job.max_attempts:
                # Expired lease with no attempts left: fail it instead of retrying forever.
                job.status = ExtractionJob.Status.FAILED
                job.error_code = "timeout"
                job.error = "Reading did not finish in time."
                job.claim_token = None
                job.lease_expires_at = None
                job.finished_at = now
                job.save()
                continue
            job.status = ExtractionJob.Status.PROCESSING
            job.attempts += 1
            job.claim_token = uuid.uuid4()
            job.lease_expires_at = now + datetime.timedelta(seconds=settings.RECEIPT_LEASE_SECONDS)
            job.available_at = None
            job.started_at = now
            job.save()
            return job, job.claim_token


def _record_usage(job, usage):
    if not usage:
        return
    history = dict(job.usage or {})
    attempts = list(history.get("attempts", []))
    attempts.append({k: usage.get(k) for k in ("input_tokens", "output_tokens", "request_id", "stop_reason")})
    history["attempts"] = attempts
    history["input_tokens"] = sum((a.get("input_tokens") or 0) for a in attempts)
    history["output_tokens"] = sum((a.get("output_tokens") or 0) for a in attempts)
    job.usage = history


def finish_success(job_id, token, data, model_version="", usage=None):
    """Store a normalised result if this attempt still owns the job. Returns the job or None if superseded."""
    with transaction.atomic():
        job = ExtractionJob.objects.select_for_update().get(pk=job_id)
        if job.claim_token != token or job.status != ExtractionJob.Status.PROCESSING:
            logger.info("Ignoring late result for job %s", job_id)
            return None
        draft = ReceiptDraft.objects.select_for_update().get(pk=job.draft_id)
        job.status = ExtractionJob.Status.SUCCEEDED
        job.draft_json = data
        job.warnings = data.get("extraction", {}).get("warnings", [])
        job.model_version = model_version[:80]
        _record_usage(job, usage)
        job.claim_token = None
        job.lease_expires_at = None
        job.finished_at = timezone.now()
        job.error_code = job.error = ""
        if not draft.is_open:
            job.result_state = ExtractionJob.ResultState.DISCARDED
        elif draft.version == job.requested_draft_version:
            draft.data = {**data, "extraction": {**data.get("extraction", {}), "job_id": job.pk,
                                                 "model": job.model_version, "adapter": job.adapter}}
            draft.version += 1
            draft.save(update_fields=["data", "version", "updated_at"])
            job.result_state = ExtractionJob.ResultState.APPLIED
        else:
            job.result_state = ExtractionJob.ResultState.HELD
        job.save()
        return job


def finish_failure(job_id, token, error: ExtractionError):
    """Record a failed attempt. Retryable errors requeue once (bounded); others fail."""
    with transaction.atomic():
        job = ExtractionJob.objects.select_for_update().get(pk=job_id)
        if job.claim_token != token or job.status != ExtractionJob.Status.PROCESSING:
            return None
        _record_usage(job, getattr(error, "usage", None))
        job.error_code = error.code[:40]
        job.error = error.message[:300]
        job.claim_token = None
        job.lease_expires_at = None
        if error.retryable and job.attempts < job.max_attempts:
            job.status = ExtractionJob.Status.QUEUED
            job.available_at = timezone.now() + datetime.timedelta(seconds=settings.RECEIPT_RETRY_DELAY_SECONDS)
        else:
            job.status = ExtractionJob.Status.FAILED
            job.finished_at = timezone.now()
        job.save()
        return job


def run_claimed_job(job, token, today=None):
    """Call the provider outside any transaction, then finish under the claim token."""
    extractor = get_extractor()
    if extractor is None:
        return finish_failure(job.pk, token, ExtractionError(
            "not_configured", "Automatic extraction not configured."))
    try:
        result = extractor.extract(job.document)
    except ExtractionError as error:
        return finish_failure(job.pk, token, error)
    except Exception as exc:  # noqa: BLE001 - never leak details; keep the worker alive
        logger.error("Receipt job %s failed with %s", job.pk, type(exc).__name__)
        return finish_failure(job.pk, token, ExtractionError("internal", "Reading failed unexpectedly."))
    try:
        data = normalise(result.raw, today=today or timezone.localdate())
    except NormaliseError:
        error = ExtractionError("malformed", "The reading service returned an unusable result.")
        error.usage = result.usage
        return finish_failure(job.pk, token, error)
    return finish_success(job.pk, token, data, result.model_version, result.usage)


def process_available(max_jobs=None, now=None):
    """Process claimable jobs until none remain (or ``max_jobs``). Returns the number processed."""
    processed = 0
    while max_jobs is None or processed < max_jobs:
        claimed = claim_next_job(now=now)
        if claimed is None:
            break
        job, token = claimed
        run_claimed_job(job, token)
        processed += 1
    return processed


def apply_held_result(owner, job, expected_version):
    """Explicitly replace the draft's values with a held (late) reading."""
    with transaction.atomic():
        locked_job = ExtractionJob.objects.select_for_update().get(pk=job.pk, document__owner=owner)
        draft = ReceiptDraft.objects.select_for_update().get(pk=locked_job.draft_id, owner=owner)
        if not draft.is_open:
            raise BusinessRuleError("This receipt has already been handled.")
        if parse_version(expected_version) != draft.version:
            raise StaleObjectError()
        if locked_job.status != ExtractionJob.Status.SUCCEEDED or locked_job.result_state != ExtractionJob.ResultState.HELD:
            raise BusinessRuleError("There is no held reading to apply.")
        data = locked_job.draft_json or {}
        draft.data = {**data, "extraction": {**data.get("extraction", {}), "job_id": locked_job.pk,
                                             "model": locked_job.model_version, "adapter": locked_job.adapter}}
        draft.version += 1
        draft.save(update_fields=["data", "version", "updated_at"])
        locked_job.result_state = ExtractionJob.ResultState.APPLIED
        locked_job.save(update_fields=["result_state", "updated_at"])
        return draft


def job_state(job, now=None):
    """Plain dict for the polling endpoint and templates."""
    if job is None:
        return {"status": "none"}
    now = now or timezone.now()
    waiting = (now - job.created_at).total_seconds()
    return {
        "id": job.pk,
        "status": job.status,
        "label": job.get_status_display(),
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "result_state": job.result_state,
        "error": job.error,
        "error_code": job.error_code,
        "stale_queue": job.status == ExtractionJob.Status.QUEUED and job.attempts == 0
        and waiting > settings.RECEIPT_STALE_QUEUE_SECONDS,
        "usage": {k: job.usage.get(k) for k in ("input_tokens", "output_tokens")} if job.usage else {},
        "model": job.model_version,
        "adapter": job.adapter,
    }
