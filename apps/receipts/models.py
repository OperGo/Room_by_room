"""Receipt evidence, extraction jobs and editable drafts.

Nothing in this app contributes to cost totals. Only ``costs.Purchase`` rows
created by ``costs.services.post_purchase`` (from a confirmed draft or manual
entry) are counted.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ReceiptDocumentQuerySet(models.QuerySet):
    def for_owner(self, user):
        return self.filter(owner=user)


class ReceiptDocument(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="receipt_documents")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    storage_key = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=120, blank=True)
    checksum = models.CharField(max_length=64, db_index=True)
    mime = models.CharField(max_length=40)
    size = models.PositiveIntegerField()
    page_count = models.PositiveSmallIntegerField(null=True, blank=True)
    preview_key = models.CharField(max_length=255, blank=True, help_text="Browser-viewable JPEG for HEIC originals.")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ReceiptDocumentQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_pdf(self):
        return self.mime == "application/pdf"


class ExtractionJobQuerySet(models.QuerySet):
    def for_owner(self, user):
        return self.filter(document__owner=user)


class ExtractionJob(models.Model):
    """Persisted extraction work item, processed by ``manage.py process_receipts`` (never in a web request).

    A job never creates cost. Its result is applied to the draft only when the draft
    is still open and unchanged since reading was requested; otherwise it is held.
    """

    class Status(models.TextChoices):
        QUEUED = "queued", "Waiting to be read"
        PROCESSING = "processing", "Reading"
        SUCCEEDED = "succeeded", "Read"
        FAILED = "failed", "Could not be read"

    class ResultState(models.TextChoices):
        NONE = "none", "No result"
        APPLIED = "applied", "Applied to the draft"
        HELD = "held", "Held: draft changed while reading"
        DISCARDED = "discarded", "Not applied: receipt already handled"

    document = models.ForeignKey(ReceiptDocument, on_delete=models.CASCADE, related_name="jobs")
    draft = models.ForeignKey("receipts.ReceiptDraft", on_delete=models.CASCADE, related_name="jobs", null=True)
    requested_draft_version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    adapter = models.CharField(max_length=40, blank=True)
    model_version = models.CharField(max_length=80, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=2)
    claim_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    available_at = models.DateTimeField(null=True, blank=True, help_text="Earliest time a retry may be claimed.")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    draft_json = models.JSONField(null=True, blank=True, help_text="Normalised draft values (never read by cost totals).")
    warnings = models.JSONField(default=list, blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    error = models.CharField(max_length=300, blank=True)
    usage = models.JSONField(default=dict, blank=True)
    result_state = models.CharField(max_length=10, choices=ResultState.choices, default=ResultState.NONE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ExtractionJobQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # At most one live job per document: double clicks cannot queue repeats.
            models.UniqueConstraint(
                fields=["document"], condition=Q(status__in=["queued", "processing"]), name="one_active_job_per_document"
            ),
            models.CheckConstraint(condition=Q(attempts__lte=models.F("max_attempts")), name="job_attempts_bounded"),
        ]

    @property
    def is_active(self):
        return self.status in (self.Status.QUEUED, self.Status.PROCESSING)


class ReceiptDraftQuerySet(models.QuerySet):
    def for_owner(self, user):
        return self.filter(owner=user)


class ReceiptDraft(models.Model):
    class ReviewStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed as purchase"
        ATTACHED = "attached", "Attached to existing purchase"
        DISCARDED = "discarded", "Discarded"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="receipt_drafts")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    document = models.OneToOneField(ReceiptDocument, on_delete=models.CASCADE, related_name="draft")
    data = models.JSONField(default=dict, blank=True, help_text="Editable draft values; never read by cost totals.")
    review_status = models.CharField(max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.DRAFT)
    attached_purchase = models.ForeignKey(
        "costs.Purchase", null=True, blank=True, on_delete=models.SET_NULL, related_name="attached_drafts"
    )
    duplicate_acknowledged = models.BooleanField(default=False)
    context_project = models.ForeignKey(
        "projects.Project", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="The owner's project this receipt was started from. Only pre-selects the 'Assign unassigned "
                  "items to' choice; it never allocates or records anything by itself.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    objects = ReceiptDraftQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_open(self):
        return self.review_status == self.ReviewStatus.DRAFT
