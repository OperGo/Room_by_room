"""Project and task services. Task completion and dependencies live here."""

import uuid

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError, StaleObjectError
from apps.core.models import record_change
from apps.core.storage import private_storage
from apps.core.uploads import normalised_jpeg

from .models import Project, ProjectPhoto, Task, TaskDependency


def _check_version(obj, expected_version):
    if expected_version is not None and int(expected_version) != obj.version:
        raise StaleObjectError()


def save_project(owner, project, expected_version=None):
    """Create or update a project from a validated (unsaved) ModelForm instance."""
    with transaction.atomic():
        if project.pk:
            current = Project.objects.select_for_update().get(pk=project.pk, owner=owner)
            _check_version(current, expected_version)
            project.version = current.version + 1
        project.owner = owner
        project.save()
        return project


def project_progress(project):
    tasks = list(project.tasks.countable().values_list("status", flat=True))
    total = len(tasks)
    done = sum(1 for status in tasks if status == Task.Status.DONE)
    return {"done": done, "total": total, "percent": int(done * 100 / total) if total else None}


def set_project_status(owner, project, status, *, expected_version=None, confirm_unfinished=False, completion_date=None):
    with transaction.atomic():
        locked = Project.objects.select_for_update().get(pk=project.pk, owner=owner)
        _check_version(locked, expected_version)
        if status not in Project.Status.values:
            raise BusinessRuleError("Unknown status.")
        if status == Project.Status.COMPLETED:
            open_count = locked.tasks.filter(status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS]).count()
            if open_count and not confirm_unfinished:
                raise BusinessRuleError(
                    f"{open_count} task{'s are' if open_count != 1 else ' is'} still unfinished. "
                    "Confirm that you want to complete the project anyway."
                )
            locked.completion_date = completion_date or locked.completion_date or timezone.localdate()
            if locked.start_date and locked.completion_date < locked.start_date:
                locked.completion_date = locked.start_date
        before = {"status": locked.status}
        locked.status = status
        locked.version += 1
        locked.save()
        record_change(owner, locked, "status_changed", before, {"status": status})
        return locked


# --------------------------------------------------------------------------- tasks


def save_task(owner, task, expected_version=None):
    """Create or update a task's descriptive fields. Status changes use the functions below."""
    if task.project.owner_id != owner.pk:
        raise BusinessRuleError("Unknown project.")
    with transaction.atomic():
        if task.pk:
            current = Task.objects.select_for_update().get(pk=task.pk, project__owner=owner)
            _check_version(current, expected_version)
            task.status = current.status
            task.completed_at = current.completed_at
            task.completion_override_note = current.completion_override_note
            task.version = current.version + 1
        else:
            last = task.project.tasks.order_by("-position").values_list("position", flat=True).first()
            task.position = (last or 0) + 1
        task.save()
        return task


def _lock_task(owner, task, expected_version=None):
    locked = Task.objects.select_for_update().select_related("project").get(pk=task.pk, project__owner=owner)
    _check_version(locked, expected_version)
    return locked


def complete_task(owner, task, *, override_note="", expected_version=None):
    """Mark a task done. Open prerequisites block completion unless overridden with a note."""
    with transaction.atomic():
        locked = _lock_task(owner, task, expected_version)
        if locked.status == Task.Status.DONE:
            return locked
        if locked.status == Task.Status.CANCELLED:
            raise BusinessRuleError("Reopen this cancelled task before completing it.")
        blocking = [
            f"{title} (cancelled)" if status == Task.Status.CANCELLED else title
            for title, status in locked.open_prerequisites().values_list("title", "status")
        ]
        override_note = (override_note or "").strip()
        if blocking and not override_note:
            raise BusinessRuleError(
                "Waiting on: " + ", ".join(blocking) + ". Finish those first, remove the dependency, "
                "or add a note explaining the override."
            )
        before = {"status": locked.status}
        locked.status = Task.Status.DONE
        locked.completed_at = timezone.now()
        locked.completion_override_note = override_note if blocking else ""
        locked.version += 1
        locked.save()
        after = {"status": locked.status}
        if blocking:
            after["override_prerequisites"] = blocking
        record_change(owner, locked, "completed", before, after, locked.completion_override_note)
        return locked


def set_task_status(owner, task, status, *, expected_version=None):
    """Move a task to to-do, in progress or cancelled. History is kept in ChangeEvent."""
    if status == Task.Status.DONE:
        raise BusinessRuleError("Use Complete to finish a task.")
    if status not in Task.Status.values:
        raise BusinessRuleError("Unknown status.")
    with transaction.atomic():
        locked = _lock_task(owner, task, expected_version)
        before = {"status": locked.status}
        if locked.completed_at:
            before["completed_at"] = locked.completed_at.isoformat()
        locked.status = status
        locked.completed_at = None
        locked.completion_override_note = ""
        locked.version += 1
        locked.save()
        record_change(owner, locked, "status_changed", before, {"status": status})
        return locked


def toggle_weekend(owner, task, saturday):
    with transaction.atomic():
        locked = _lock_task(owner, task)
        locked.weekend_date = None if locked.weekend_date == saturday else saturday
        locked.version += 1
        locked.save(update_fields=["weekend_date", "version", "updated_at"])
        return locked


def _reaches(start, target, edges):
    """True if ``target`` is reachable from ``start`` following ``edges`` (task -> prerequisites)."""
    stack, seen = [start], set()
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(edges.get(node, ()))
    return False


def set_dependencies(owner, task, prerequisites):
    """Replace ``task``'s prerequisites. Rejects cross-project links and cycles.

    Completion history is never changed: a task completed earlier stays done
    even if a newly added prerequisite is still open (the UI flags it).
    """
    with transaction.atomic():
        locked = _lock_task(owner, task)
        prereq_ids = set()
        for prereq in prerequisites:
            if prereq.project_id != locked.project_id:
                raise BusinessRuleError("Dependencies must be tasks in the same project.")
            if prereq.pk == locked.pk:
                raise BusinessRuleError("A task cannot depend on itself.")
            prereq_ids.add(prereq.pk)
        edges = {}
        for t_id, p_id in TaskDependency.objects.filter(task__project=locked.project).exclude(task=locked).values_list(
            "task_id", "prerequisite_id"
        ):
            edges.setdefault(t_id, set()).add(p_id)
        edges[locked.pk] = prereq_ids
        for p_id in prereq_ids:
            if _reaches(p_id, locked.pk, edges):
                title = Task.objects.get(pk=p_id).title
                raise BusinessRuleError(f"“{title}” already depends on this task, so it cannot also be a prerequisite.")
        before = sorted(locked.prerequisites().values_list("title", flat=True))
        TaskDependency.objects.filter(task=locked).exclude(prerequisite_id__in=prereq_ids).delete()
        existing = set(TaskDependency.objects.filter(task=locked).values_list("prerequisite_id", flat=True))
        TaskDependency.objects.bulk_create(
            TaskDependency(task=locked, prerequisite_id=p_id) for p_id in prereq_ids - existing
        )
        after = sorted(locked.prerequisites().values_list("title", flat=True))
        if before != after:
            record_change(owner, locked, "dependencies_changed", {"prerequisites": before}, {"prerequisites": after})
        return locked


def ready_tasks(owner):
    """Open tasks in planned/active projects whose prerequisites are all done."""
    open_statuses = [Task.Status.TODO, Task.Status.IN_PROGRESS]
    return (
        Task.objects.filter(
            project__owner=owner,
            project__status__in=[Project.Status.PLANNED, Project.Status.ACTIVE],
            status__in=open_statuses,
        )
        .exclude(prerequisite_links__prerequisite__status__in=open_statuses + [Task.Status.CANCELLED])
        .select_related("project")
        .order_by("due_date", "project__title", "position")
    )


# --------------------------------------------------------------------------- photos


def add_photo(owner, project, validated_upload, caption="", is_sample=False):
    if project.owner_id != owner.pk:
        raise BusinessRuleError("Unknown project.")
    jpeg = normalised_jpeg(validated_upload.content)
    key = f"photos/{owner.pk}/{uuid.uuid4().hex}.jpg"
    from django.core.files.base import ContentFile

    stored_key = private_storage().save(key, ContentFile(jpeg))
    try:
        with transaction.atomic():
            photo = ProjectPhoto.objects.create(
                project=project, storage_key=stored_key, caption=caption[:200], is_sample=is_sample,
                width=validated_upload.width, height=validated_upload.height,
            )
            locked = Project.objects.select_for_update().get(pk=project.pk)
            if locked.cover_photo_id is None:
                locked.cover_photo = photo
                locked.save(update_fields=["cover_photo", "updated_at"])
            return photo
    except Exception:
        private_storage().delete(stored_key)
        raise


def delete_photo(owner, photo):
    """Deleting a photo never touches costs. The file is removed after commit."""
    with transaction.atomic():
        locked = ProjectPhoto.objects.select_for_update().get(pk=photo.pk, project__owner=owner)
        key = locked.storage_key
        Project.objects.filter(cover_photo=locked).update(cover_photo=None)
        locked.delete()
        transaction.on_commit(lambda: private_storage().delete(key))


def set_cover(owner, project, photo):
    if photo is not None and photo.project_id != project.pk:
        raise BusinessRuleError("That photo belongs to another project.")
    with transaction.atomic():
        locked = Project.objects.select_for_update().get(pk=project.pk, owner=owner)
        locked.cover_photo = photo
        locked.save(update_fields=["cover_photo", "updated_at"])
        return locked
