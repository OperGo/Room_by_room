from collections import OrderedDict

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.dates import local_today
from apps.core.exceptions import StaleObjectError
from apps.core.shortcuts import parse_uuid, flash_errors, owned, safe_next
from apps.projects.models import Project

from .forms import ShoppingItemForm
from .models import ShoppingItem


def _group(items, by):
    groups = OrderedDict()
    for item in items:
        if by == "retailer":
            key = item.retailer or "Any retailer"
        else:
            key = item.project.title if item.project else "Shared"
        groups.setdefault(key, []).append(item)
    return sorted(groups.items(), key=lambda kv: (kv[0] in {"Shared", "Any retailer"}, kv[0].lower()))


def shopping_list(request):
    group_by = request.GET.get("group", "project")
    if group_by not in {"project", "retailer"}:
        group_by = "project"
    items = ShoppingItem.objects.for_owner(request.user).select_related("project", "task", "purchase_line__purchase")
    project_filter = request.GET.get("project")
    project = None
    if project_filter:
        project = Project.objects.for_owner(request.user).filter(uuid=parse_uuid(project_filter)).first()
        if project:
            items = items.filter(project=project)
    to_buy = [i for i in items if not i.is_bought]
    bought = sorted([i for i in items if i.is_bought], key=lambda i: i.purchased_at, reverse=True)
    return render(request, "shopping/list.html", {
        "groups": _group(to_buy, group_by),
        "today": local_today(),
        "bought": bought[:50],
        "group_by": group_by,
        "to_buy_count": len(to_buy),
        "filter_project": project,
        "form": ShoppingItemForm(request.user, initial={"quantity": 1, "project": project}),
    })


def item_create(request):
    initial = {"quantity": 1}
    if request.GET.get("project"):
        initial["project"] = Project.objects.for_owner(request.user).filter(uuid=parse_uuid(request.GET["project"])).first()
    form = ShoppingItemForm(request.user, request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.owner = request.user
        item.save()
        messages.success(request, f"Added “{item.description}”.")
        return redirect("shopping:list")
    return render(request, "shopping/form.html", {"form": form, "creating": True})


def item_edit(request, uuid):
    item = owned(ShoppingItem, request.user, uuid=uuid)
    form = ShoppingItemForm(request.user, request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            current = ShoppingItem.objects.select_for_update().get(pk=item.pk)
            if form.cleaned_data.get("version") not in (None, current.version):
                flash_errors(request, StaleObjectError())
                return redirect("shopping:edit", uuid=uuid)
            updated = form.save(commit=False)
            updated.version = current.version + 1
            updated.save()
        messages.success(request, "Item saved.")
        return redirect("shopping:list")
    return render(request, "shopping/form.html", {"form": form, "item": item})


@require_POST
def item_toggle_bought(request, uuid):
    """Ticking an item as bought records no spending (use Add purchase for that)."""
    item = owned(ShoppingItem, request.user, uuid=uuid)
    with transaction.atomic():
        item = ShoppingItem.objects.select_for_update().get(pk=item.pk)
        if item.purchased_at and item.purchase_line_id:
            messages.error(request, "This item is linked to a recorded purchase; correct the purchase instead.")
            return redirect("shopping:list")
        item.purchased_at = None if item.purchased_at else timezone.now()
        item.version += 1
        item.save(update_fields=["purchased_at", "version", "updated_at"])
    if item.purchased_at:
        messages.success(request, f"Marked “{item.description}” bought. No cost was recorded.")
    return redirect(safe_next(request, reverse("shopping:list")))


@require_POST
def item_delete(request, uuid):
    item = owned(ShoppingItem, request.user, uuid=uuid)
    item.delete()
    messages.success(request, f"Removed “{item.description}”. Any recorded purchase is unaffected.")
    return redirect("shopping:list")
