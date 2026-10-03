import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ProjectQuerySet(models.QuerySet):
    def for_owner(self, user):
        return self.filter(owner=user)


class Project(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(max_length=120)
    room = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    cover_photo = models.ForeignKey(
        "projects.ProjectPhoto", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.CheckConstraint(condition=Q(budget__isnull=True) | Q(budget__gte=0), name="project_budget_non_negative"),
            models.CheckConstraint(
                condition=Q(start_date__isnull=True) | Q(completion_date__isnull=True) | Q(completion_date__gte=models.F("start_date")),
                name="project_completion_after_start",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.status in (self.Status.PLANNED, self.Status.ACTIVE)


class TaskQuerySet(models.QuerySet):
    def for_owner(self, user):
        return self.filter(project__owner=user)

    def countable(self):
        return self.exclude(status=Task.Status.CANCELLED)


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To do"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(max_length=160)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TODO)
    estimated_minutes = models.PositiveIntegerField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    weekend_date = models.DateField(null=True, blank=True, help_text="Saturday of the weekend this task is planned for.")
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_override_note = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    objects = TaskQuerySet.as_manager()

    class Meta:
        ordering = ["position", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(estimated_minutes__isnull=True) | Q(estimated_minutes__gt=0), name="task_estimate_positive"
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.status in (self.Status.TODO, self.Status.IN_PROGRESS)

    def prerequisites(self):
        return Task.objects.filter(dependents_links__task=self)

    def open_prerequisites(self):
        # A cancelled prerequisite cannot be done, so it no longer blocks.
        return self.prerequisites().filter(status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS])

    @property
    def is_blocked(self):
        return self.is_open and self.open_prerequisites().exists()


class TaskDependency(models.Model):
    """``task`` cannot be completed until ``prerequisite`` is done."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="prerequisite_links")
    prerequisite = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="dependents_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["task", "prerequisite"], name="unique_task_dependency"),
            models.CheckConstraint(condition=~Q(task=models.F("prerequisite")), name="task_dependency_not_self"),
        ]


class ProjectPhotoQuerySet(models.QuerySet):
    def for_owner(self, user):
        return self.filter(project__owner=user)


class ProjectPhoto(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="photos")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    storage_key = models.CharField(max_length=255)
    caption = models.CharField(max_length=200, blank=True)
    is_sample = models.BooleanField(default=False, help_text="Illustrative sample image, not the owner's home.")
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ProjectPhotoQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
