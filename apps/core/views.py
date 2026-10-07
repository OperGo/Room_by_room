from django.contrib.auth.decorators import login_not_required
from django.db.models import F, Max
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static

from apps.core.dates import local_today, this_weekend_saturday
from apps.costs.selectors import project_cost_summaries
from apps.projects.models import Project
from apps.projects.services import project_progress, ready_tasks
from apps.receipts.models import ReceiptDraft


def home(request):
    owner = request.user
    projects = list(
        Project.objects.for_owner(owner)
        .filter(status__in=[Project.Status.ACTIVE, Project.Status.PLANNED])
        .select_related("cover_photo")
        .annotate(last_activity=Max("tasks__completed_at"))
        .order_by("status", F("last_activity").desc(nulls_last=True), "-updated_at")
    )
    costs = project_cost_summaries(owner, projects)
    for project in projects:
        project.progress = project_progress(project)
        project.costs = costs[project.pk]  # confirmed records and opening estimates only; drafts never count
        project.net_cost = project.costs.net
    featured = next((p for p in projects if p.status == Project.Status.ACTIVE), projects[0] if projects else None)
    others = [p for p in projects if p is not featured]
    saturday = this_weekend_saturday()
    ready = list(ready_tasks(owner)[:40])
    weekend = [t for t in ready if t.weekend_date == saturday]
    rest = [t for t in ready if t.weekend_date != saturday][:5]
    drafts = ReceiptDraft.objects.for_owner(owner).filter(review_status=ReceiptDraft.ReviewStatus.DRAFT).count()
    return render(request, "core/home.html", {
        "today": local_today(),
        "featured": featured,
        "others": others,
        "weekend_tasks": weekend,
        "ready_tasks": rest,
        "saturday": saturday,
        "open_drafts": drafts,
    })


@login_not_required
def manifest(request):
    return JsonResponse({
        "name": "Room by Room",
        "short_name": "Room by Room",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#F7F5F0",
        "theme_color": "#23483C",
        "icons": [{"src": static("img/icon-512.png"), "sizes": "512x512", "type": "image/png"}],
    }, content_type="application/manifest+json")


@login_not_required
def healthz(request):
    """Liveness/readiness for Render: database reachable. Returns no user data."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # noqa: BLE001
        return JsonResponse({"status": "unavailable"}, status=503)
    response = JsonResponse({"status": "ok"})
    response["Cache-Control"] = "no-store"
    return response
