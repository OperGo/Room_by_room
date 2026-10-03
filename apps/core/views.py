from django.contrib.auth.decorators import login_not_required
from django.db.models import F, Max
from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static

from apps.core.dates import local_today, this_weekend_saturday
from apps.costs.selectors import project_net_costs
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
    costs = project_net_costs(owner, projects)
    for project in projects:
        project.progress = project_progress(project)
        project.net_cost = costs[project.pk]
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
