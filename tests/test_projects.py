import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.core.exceptions import BusinessRuleError, StaleObjectError
from apps.core.models import ChangeEvent
from apps.projects import services
from apps.projects.models import Project, ProjectPhoto, Task, TaskDependency

from .conftest import image_bytes, upload

pytestmark = pytest.mark.django_db


def make_task(owner, project, title, **kw):
    return services.save_task(owner, Task(project=project, title=title, **kw))


def test_create_and_edit_project_with_historical_dates(client_owner, owner):
    response = client_owner.post(reverse("projects:create"), {
        "title": "Bathroom 2019", "room": "Bathroom", "status": "completed", "budget": "750.00",
        "start_date": "2019-02-01", "completion_date": "2019-05-30", "notes": "<script>alert(1)</script>",
    })
    project = Project.objects.get(owner=owner)
    assert response.status_code == 302
    assert project.start_date == datetime.date(2019, 2, 1) and project.status == "completed"
    detail = client_owner.get(reverse("projects:detail", args=[project.uuid]))
    assert b"<script>alert(1)</script>" not in detail.content  # escaped
    assert b"&lt;script&gt;" in detail.content
    response = client_owner.post(reverse("projects:edit", args=[project.uuid]), {
        "title": "Bathroom refit", "room": "Bathroom", "budget": "800", "start_date": "2019-02-01",
        "completion_date": "2019-05-30", "notes": "", "version": project.version,
    })
    project.refresh_from_db()
    assert project.title == "Bathroom refit" and project.version == 2
    # Searchable and editable later.
    listing = client_owner.get(reverse("projects:list"), {"q": "refit"})
    assert b"Bathroom refit" in listing.content


def test_project_completion_before_start_rejected(client_owner, owner):
    response = client_owner.post(reverse("projects:create"), {
        "title": "Bad dates", "status": "active", "start_date": "2026-05-01", "completion_date": "2026-04-01",
    })
    assert response.status_code == 200
    assert not Project.objects.filter(owner=owner).exists()


def test_stale_project_edit_is_refused(client_owner, owner):
    project = Project.objects.create(owner=owner, title="Office")
    stale_version = project.version
    services.save_project(owner, Project.objects.get(pk=project.pk), stale_version)
    response = client_owner.post(reverse("projects:edit", args=[project.uuid]), {
        "title": "Overwrite", "version": stale_version,
    }, follow=True)
    assert b"changed since you opened it" in response.content
    project.refresh_from_db()
    assert project.title == "Office"


def test_progress_counts_done_over_non_cancelled(owner):
    project = Project.objects.create(owner=owner, title="Office")
    assert services.project_progress(project) == {"done": 0, "total": 0, "percent": None}
    tasks = [make_task(owner, project, f"T{i}") for i in range(4)]
    services.complete_task(owner, tasks[0])
    services.set_task_status(owner, tasks[1], "cancelled")
    assert services.project_progress(project) == {"done": 1, "total": 3, "percent": 33}


def test_dependency_cycles_and_cross_project_rejected(owner):
    a_project = Project.objects.create(owner=owner, title="A")
    other = Project.objects.create(owner=owner, title="B")
    a, b, c = (make_task(owner, a_project, t) for t in "abc")
    services.set_dependencies(owner, b, [a])
    services.set_dependencies(owner, c, [b])
    with pytest.raises(BusinessRuleError):
        services.set_dependencies(owner, a, [c])  # a -> c -> b -> a
    with pytest.raises(BusinessRuleError):
        services.set_dependencies(owner, a, [a])
    x = make_task(owner, other, "x")
    with pytest.raises(BusinessRuleError):
        services.set_dependencies(owner, a, [x])
    assert TaskDependency.objects.count() == 2


def test_completion_requires_prerequisites_or_override(owner):
    project = Project.objects.create(owner=owner, title="Office")
    sand = make_task(owner, project, "Sand")
    prime = make_task(owner, project, "Prime")
    services.set_dependencies(owner, prime, [sand])
    assert prime.is_blocked
    with pytest.raises(BusinessRuleError):
        services.complete_task(owner, prime)
    services.complete_task(owner, prime, override_note="Primed the back panels early")
    prime.refresh_from_db()
    assert prime.status == "done" and prime.completion_override_note
    assert ChangeEvent.objects.filter(subject_id=str(prime.uuid), action="completed").exists()


def test_cancelled_prerequisite_still_blocks_until_removed_or_overridden(owner):
    project = Project.objects.create(owner=owner, title="Office")
    a, b = make_task(owner, project, "a"), make_task(owner, project, "b")
    services.set_dependencies(owner, b, [a])
    services.set_task_status(owner, a, "cancelled")
    assert b.is_blocked
    assert b not in services.ready_tasks(owner)
    with pytest.raises(BusinessRuleError) as exc:
        services.complete_task(owner, b)
    assert "a (cancelled)" in str(exc.value)
    # Override with a recorded note.
    services.complete_task(owner, b, override_note="Prerequisite no longer needed")
    event = ChangeEvent.objects.get(subject_id=str(b.uuid), action="completed")
    assert event.after["override_prerequisites"] == ["a (cancelled)"]
    assert event.reason == "Prerequisite no longer needed"
    # Or remove the dependency: the task becomes ready.
    c = make_task(owner, project, "c")
    services.set_dependencies(owner, c, [a])
    assert c not in services.ready_tasks(owner)
    services.set_dependencies(owner, c, [])
    assert c in services.ready_tasks(owner)
    # Completion history is preserved when dependencies change.
    services.set_dependencies(owner, b, [])
    b.refresh_from_db()
    assert b.status == "done" and b.completion_override_note == "Prerequisite no longer needed"


def test_changing_dependencies_keeps_completion_history(owner):
    project = Project.objects.create(owner=owner, title="Office")
    a, b = make_task(owner, project, "a"), make_task(owner, project, "b")
    services.complete_task(owner, b)
    services.set_dependencies(owner, b, [a])
    b.refresh_from_db()
    assert b.status == "done" and b.completed_at is not None


def test_reopen_records_previous_completion(owner):
    project = Project.objects.create(owner=owner, title="Office")
    a = make_task(owner, project, "a")
    services.complete_task(owner, a)
    services.set_task_status(owner, a, "todo")
    event = ChangeEvent.objects.get(subject_id=str(a.uuid), action="status_changed")
    assert event.before["status"] == "done" and "completed_at" in event.before


def test_stale_task_completion(owner):
    project = Project.objects.create(owner=owner, title="Office")
    a = make_task(owner, project, "a")
    with pytest.raises(StaleObjectError):
        services.complete_task(owner, a, expected_version=a.version + 5)


def test_ready_tasks_excludes_blocked_and_inactive_projects(owner):
    active = Project.objects.create(owner=owner, title="Active")
    archived = Project.objects.create(owner=owner, title="Old", status="archived")
    a, b = make_task(owner, active, "Fill"), make_task(owner, active, "Prime")
    services.set_dependencies(owner, b, [a])
    make_task(owner, archived, "Hidden")
    assert [t.title for t in services.ready_tasks(owner)] == ["Fill"]
    services.complete_task(owner, a)
    assert [t.title for t in services.ready_tasks(owner)] == ["Prime"]


def test_complete_project_with_unfinished_tasks_needs_confirmation(client_owner, owner):
    project = Project.objects.create(owner=owner, title="Office")
    make_task(owner, project, "Paint")
    response = client_owner.post(reverse("projects:status", args=[project.uuid]), {"status": "completed", "version": project.version})
    assert b"still unfinished" in response.content
    project.refresh_from_db()
    assert project.status == "active"
    client_owner.post(reverse("projects:status", args=[project.uuid]),
                      {"status": "completed", "version": project.version, "confirm_unfinished": "1"})
    project.refresh_from_db()
    assert project.status == "completed" and project.completion_date is not None
    assert project.tasks.count() == 1


def test_complete_task_view_with_override(client_owner, owner):
    project = Project.objects.create(owner=owner, title="Office")
    a, b = make_task(owner, project, "a"), make_task(owner, project, "b")
    services.set_dependencies(owner, b, [a])
    client_owner.post(reverse("projects:task_complete", args=[b.uuid]), {"version": b.version})
    b.refresh_from_db()
    assert b.status == "todo"
    client_owner.post(reverse("projects:task_complete", args=[b.uuid]), {"version": b.version, "override_note": "Done early"})
    b.refresh_from_db()
    assert b.status == "done"


def test_photo_upload_normalises_and_delete_keeps_costs(client_owner, owner, private_storage_tmp):
    from apps.costs.selectors import project_cost_summary
    from apps.costs.services import post_purchase

    from .conftest import line, purchase_input, to

    project = Project.objects.create(owner=owner, title="Office")
    post_purchase(owner, purchase_input([line("MDF", "32.00", [to(project, "32.00")])]))
    response = client_owner.post(reverse("projects:photo_upload", args=[project.uuid]),
                                 {"photo": upload("wall.jpg", image_bytes(exif_orientation=6)), "caption": "Before"})
    assert response.status_code == 302
    photo = ProjectPhoto.objects.get()
    project.refresh_from_db()
    assert project.cover_photo == photo
    stored = (private_storage_tmp / photo.storage_key).read_bytes()
    from PIL import Image
    import io

    im = Image.open(io.BytesIO(stored))
    assert im.size == (80, 120)  # rotated upright by EXIF orientation 6
    assert not im.getexif().get(0x0112)  # metadata stripped
    client_owner.post(reverse("projects:photo_delete", args=[photo.uuid]))
    assert not ProjectPhoto.objects.exists()
    project.refresh_from_db()
    assert project.cover_photo is None
    assert project_cost_summary(project).net == Decimal("32.00")


def test_photo_upload_rejects_non_image(client_owner, owner):
    project = Project.objects.create(owner=owner, title="Office")
    response = client_owner.post(reverse("projects:photo_upload", args=[project.uuid]),
                                 {"photo": upload("evil.jpg", b"<?php echo 1; ?>")})
    assert response.status_code == 200
    assert b"Upload a JPEG, PNG or iPhone HEIC photo" in response.content
    assert not ProjectPhoto.objects.exists()


def test_home_shows_ready_tasks_and_featured_project(client_owner, owner):
    project = Project.objects.create(owner=owner, title="Office cabinetry")
    make_task(owner, project, "Fill and sand joints")
    response = client_owner.get(reverse("core:home"))
    assert b"Office cabinetry" in response.content
    assert b"Ready to start" in response.content and b"Fill and sand joints" in response.content
    assert b"0 of 1 tasks complete" in response.content


def test_weekend_selection(client_owner, owner):
    from apps.core.dates import this_weekend_saturday

    project = Project.objects.create(owner=owner, title="Office")
    t = make_task(owner, project, "Paint")
    client_owner.post(reverse("projects:task_weekend", args=[t.uuid]))
    t.refresh_from_db()
    assert t.weekend_date == this_weekend_saturday()
    assert b"Ready this weekend" in client_owner.get(reverse("core:home")).content


def test_this_weekend_saturday():
    from apps.core.dates import this_weekend_saturday

    assert this_weekend_saturday(datetime.date(2026, 10, 1)) == datetime.date(2026, 10, 3)  # Thu
    assert this_weekend_saturday(datetime.date(2026, 10, 3)) == datetime.date(2026, 10, 3)  # Sat
    assert this_weekend_saturday(datetime.date(2026, 10, 4)) == datetime.date(2026, 10, 3)  # Sun
