from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.dates import this_weekend_saturday
from apps.core.exceptions import BusinessRuleError, StaleObjectError
from apps.core.models import ChangeEvent
from apps.core.shortcuts import flash_errors, owned, safe_next
from apps.core.storage import private_storage
from apps.core.uploads import validate_image
from apps.costs.forms import OpeningBalanceForm
from apps.costs.models import OpeningCostBalance, Purchase
from apps.costs.selectors import project_cost_summary, project_net_costs, purchase_project_share
from apps.costs.services import create_opening_balance, update_opening_balance

from . import services
from .forms import DependencyForm, PhotoForm, ProjectForm, ProjectSearchForm, TaskForm
from .models import Project, ProjectPhoto, Task


def project_list(request):
    form = ProjectSearchForm(request.GET or None)
    projects = Project.objects.for_owner(request.user).select_related("cover_photo")
    if form.is_valid():
        q = form.cleaned_data["q"]
        if q:
            projects = projects.filter(Q(title__icontains=q) | Q(room__icontains=q) | Q(notes__icontains=q))
        if form.cleaned_data["status"]:
            projects = projects.filter(status=form.cleaned_data["status"])
    projects = list(projects.order_by("title"))
    costs = project_net_costs(request.user, projects)
    for project in projects:
        project.progress = services.project_progress(project)
        project.net_cost = costs[project.pk]
    groups = [
        (label, [p for p in projects if p.status == status])
        for status, label in [
            (Project.Status.ACTIVE, "Active"), (Project.Status.PLANNED, "Planned"),
            (Project.Status.COMPLETED, "Completed"), (Project.Status.ARCHIVED, "Archived"),
        ]
    ]
    return render(request, "projects/list.html", {"form": form, "groups": [g for g in groups if g[1]], "count": len(projects)})


def project_create(request):
    form = ProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        project = services.save_project(request.user, form.save(commit=False))
        messages.success(request, f"Created “{project.title}”.")
        return redirect("projects:detail", uuid=project.uuid)
    return render(request, "projects/form.html", {"form": form, "creating": True})


def project_edit(request, uuid):
    project = owned(Project, request.user, uuid=uuid)
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == "POST" and form.is_valid():
        try:
            services.save_project(request.user, form.save(commit=False), form.cleaned_data.get("version"))
        except StaleObjectError as exc:
            flash_errors(request, exc)
            return redirect("projects:edit", uuid=uuid)
        messages.success(request, "Project saved.")
        return redirect("projects:detail", uuid=uuid)
    return render(request, "projects/form.html", {"form": form, "project": project})


def project_detail(request, uuid):
    project = owned(Project, request.user, uuid=uuid)
    tab = request.GET.get("tab", "tasks")
    if tab not in {"tasks", "costs", "photos"}:
        tab = "tasks"
    tasks = list(project.tasks.prefetch_related("prerequisite_links__prerequisite"))
    for task in tasks:
        prereqs = [link.prerequisite for link in task.prerequisite_links.all()]
        task.waiting_on = [p for p in prereqs if p.is_open]
        task.done_before_prereq = task.status == Task.Status.DONE and bool(task.waiting_on)
    open_tasks = [t for t in tasks if t.is_open]
    done_tasks = [t for t in tasks if t.status == Task.Status.DONE]
    cancelled_tasks = [t for t in tasks if t.status == Task.Status.CANCELLED]
    summary = project_cost_summary(project)
    purchases = []
    if tab == "costs":
        for purchase in (
            Purchase.objects.for_owner(request.user).filter(lines__allocations__project=project).distinct()
            .order_by("-transaction_date", "-created_at")
        ):
            purchase.project_share = purchase_project_share(purchase, project)
            purchases.append(purchase)
    context = {
        "project": project,
        "tab": tab,
        "open_tasks": open_tasks,
        "done_tasks": done_tasks,
        "cancelled_tasks": cancelled_tasks,
        "progress": services.project_progress(project),
        "summary": summary,
        "purchases": purchases,
        "balances": project.opening_balances.all(),
        "photos": project.photos.all() if tab == "photos" else [],
        "saturday": this_weekend_saturday(),
        "photo_form": PhotoForm(),
        "history": ChangeEvent.objects.filter(owner=request.user, subject_type="project", subject_id=str(project.uuid))[:10],
    }
    return render(request, "projects/detail.html", context)


@require_POST
def project_status(request, uuid):
    project = owned(Project, request.user, uuid=uuid)
    status = request.POST.get("status", "")
    try:
        services.set_project_status(
            request.user, project, status,
            expected_version=request.POST.get("version"),
            confirm_unfinished=request.POST.get("confirm_unfinished") == "1",
        )
    except (BusinessRuleError, StaleObjectError) as exc:
        if isinstance(exc, BusinessRuleError) and status == Project.Status.COMPLETED:
            project.refresh_from_db()
            return render(request, "projects/confirm_complete.html", {
                "project": project, "messages_list": exc.messages,
                "open_tasks": project.tasks.filter(status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS]),
            })
        flash_errors(request, exc)
        return redirect("projects:detail", uuid=uuid)
    labels = dict(Project.Status.choices)
    messages.success(request, f"Project marked {labels[status].lower()}. Recorded costs are unchanged.")
    return redirect("projects:detail", uuid=uuid)


# --------------------------------------------------------------------------- tasks


def task_create(request, uuid):
    project = owned(Project, request.user, uuid=uuid)
    form = TaskForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.project = project
        services.save_task(request.user, task)
        messages.success(request, f"Added “{task.title}”.")
        if request.POST.get("add_another"):
            return redirect("projects:task_create", uuid=uuid)
        return redirect("projects:detail", uuid=uuid)
    return render(request, "projects/task_form.html", {"form": form, "project": project, "creating": True})


def task_detail(request, uuid):
    task = owned(Task, request.user, uuid=uuid)
    history = ChangeEvent.objects.filter(owner=request.user, subject_type="task", subject_id=str(task.uuid))[:20]
    return render(request, "projects/task_detail.html", {
        "task": task, "project": task.project,
        "prerequisites": task.prerequisites(), "waiting_on": list(task.open_prerequisites()),
        "dependents": Task.objects.filter(prerequisite_links__prerequisite=task),
        "history": history, "saturday": this_weekend_saturday(),
        "shopping": task.shopping_items.all(),
    })


def task_edit(request, uuid):
    task = owned(Task, request.user, uuid=uuid)
    form = TaskForm(request.POST or None, instance=task)
    if request.method == "POST" and form.is_valid():
        try:
            services.save_task(request.user, form.save(commit=False), form.cleaned_data.get("version"))
        except StaleObjectError as exc:
            flash_errors(request, exc)
            return redirect("projects:task_edit", uuid=uuid)
        messages.success(request, "Task saved.")
        return redirect("projects:task_detail", uuid=uuid)
    return render(request, "projects/task_form.html", {"form": form, "project": task.project, "task": task})


@require_POST
def task_complete(request, uuid):
    task = owned(Task, request.user, uuid=uuid)
    try:
        services.complete_task(
            request.user, task, override_note=request.POST.get("override_note", ""),
            expected_version=request.POST.get("version") or None,
        )
    except (BusinessRuleError, StaleObjectError) as exc:
        flash_errors(request, exc)
        return redirect(reverse("projects:task_detail", kwargs={"uuid": uuid}) + "#complete")
    messages.success(request, f"“{task.title}” done.")
    return redirect(safe_next(request, reverse("projects:detail", kwargs={"uuid": task.project.uuid})))


@require_POST
def task_status(request, uuid):
    task = owned(Task, request.user, uuid=uuid)
    try:
        services.set_task_status(request.user, task, request.POST.get("status", ""),
                                 expected_version=request.POST.get("version") or None)
    except (BusinessRuleError, StaleObjectError) as exc:
        flash_errors(request, exc)
    return redirect(safe_next(request, reverse("projects:task_detail", kwargs={"uuid": uuid})))


@require_POST
def task_weekend(request, uuid):
    task = owned(Task, request.user, uuid=uuid)
    task = services.toggle_weekend(request.user, task, this_weekend_saturday())
    messages.success(request, "Added to this weekend." if task.weekend_date else "Removed from this weekend.")
    return redirect(safe_next(request, reverse("projects:task_detail", kwargs={"uuid": uuid})))


def task_dependencies(request, uuid):
    task = owned(Task, request.user, uuid=uuid)
    form = DependencyForm(task, request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.set_dependencies(request.user, task, list(form.cleaned_data["prerequisites"]))
        except BusinessRuleError as exc:
            for message in exc.messages:
                form.add_error("prerequisites", message)
        else:
            messages.success(request, "Dependencies saved.")
            return redirect("projects:task_detail", uuid=uuid)
    return render(request, "projects/task_dependencies.html", {"form": form, "task": task, "project": task.project})


# --------------------------------------------------------------------------- photos


def photo_upload(request, uuid):
    project = owned(Project, request.user, uuid=uuid)
    form = PhotoForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            validated = validate_image(form.cleaned_data["photo"])
            services.add_photo(request.user, project, validated, caption=form.cleaned_data["caption"])
        except ValidationError as exc:
            form.add_error("photo", exc)
        else:
            messages.success(request, "Photo added.")
            return redirect(reverse("projects:detail", kwargs={"uuid": uuid}) + "?tab=photos")
    return render(request, "projects/photo_form.html", {"form": form, "project": project})


def photo_file(request, uuid):
    photo = owned(ProjectPhoto, request.user, uuid=uuid)
    storage = private_storage()
    if not storage.exists(photo.storage_key):
        raise Http404
    response = FileResponse(storage.open(photo.storage_key, "rb"), content_type="image/jpeg")
    response["Content-Disposition"] = "inline"
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_POST
def photo_delete(request, uuid):
    photo = owned(ProjectPhoto, request.user, uuid=uuid)
    project_uuid = photo.project.uuid
    services.delete_photo(request.user, photo)
    messages.success(request, "Photo deleted. Costs are unaffected.")
    return redirect(reverse("projects:detail", kwargs={"uuid": project_uuid}) + "?tab=photos")


@require_POST
def photo_cover(request, uuid):
    photo = owned(ProjectPhoto, request.user, uuid=uuid)
    clear = request.POST.get("clear") == "1"
    services.set_cover(request.user, photo.project, None if clear else photo)
    messages.success(request, "Cover photo removed." if clear else "Cover photo set.")
    return redirect(reverse("projects:detail", kwargs={"uuid": photo.project.uuid}) + "?tab=photos")


# --------------------------------------------------------------------------- opening balances


def opening_balance_create(request, uuid):
    project = owned(Project, request.user, uuid=uuid)
    form = OpeningBalanceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            create_opening_balance(request.user, project, amount=d["amount"], coverage_through=d["coverage_through"], note=d["note"])
        except BusinessRuleError as exc:
            for m in exc.messages:
                form.add_error(None, m)
        else:
            messages.success(request, "Opening balance added.")
            return redirect(reverse("projects:detail", kwargs={"uuid": uuid}) + "?tab=costs")
    return render(request, "projects/opening_balance_form.html", {"form": form, "project": project, "creating": True})


def opening_balance_edit(request, uuid):
    balance =OpeningCostBalance.objects.filter(project__owner=request.user, uuid=uuid).select_related("project").first()
    if balance is None:
        raise Http404
    initial = {"amount": balance.original_amount, "coverage_through": balance.coverage_through, "note": balance.note,
               "version": balance.version}
    form = OpeningBalanceForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            update_opening_balance(request.user, balance, d.get("version"), amount=d["amount"],
                                   coverage_through=d["coverage_through"], note=d["note"], reason=d["reason"])
        except (BusinessRuleError, StaleObjectError) as exc:
            for m in exc.messages:
                form.add_error(None, m)
        else:
            messages.success(request, "Opening balance updated.")
            return redirect(reverse("projects:detail", kwargs={"uuid": balance.project.uuid}) + "?tab=costs")
    history = ChangeEvent.objects.filter(owner=request.user, subject_type="openingcostbalance", subject_id=str(balance.uuid))
    return render(request, "projects/opening_balance_form.html", {
        "form": form, "project": balance.project, "balance": balance, "history": history,
        "decisions": balance.decisions.select_related("purchase"),
    })
