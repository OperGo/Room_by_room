from django.conf import settings
from django.db import models


class ChangeEvent(models.Model):
    """Audit trail for edits, corrections, voids and other important decisions."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="change_events")
    subject_type = models.CharField(max_length=40)
    subject_id = models.CharField(max_length=64)
    action = models.CharField(max_length=40)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["owner", "subject_type", "subject_id"])]

    def __str__(self):
        return f"{self.subject_type}:{self.subject_id} {self.action}"


def record_change(owner, subject, action, before=None, after=None, reason=""):
    return ChangeEvent.objects.create(
        owner=owner,
        subject_type=subject._meta.model_name,
        subject_id=str(getattr(subject, "uuid", subject.pk)),
        action=action,
        before=before or {},
        after=after or {},
        reason=reason or "",
    )


class StoredFile(models.Model):
    """Private file bytes kept in PostgreSQL (used by DatabaseStorage on Render).

    One durable store shared by the web service and the receipt worker, covered by the
    same database backups. Never served directly: owner-checked views stream it.
    """

    name = models.CharField(max_length=255, unique=True)
    content = models.BinaryField()
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
