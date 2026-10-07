"""Read-only cost totals. Only confirmed purchases/refunds and opening balances count.

Receipt drafts and extraction output are never read here.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q, Sum

from apps.core.money import ZERO

from .models import CostAllocation, OpeningCostBalance, Purchase


def _sum(qs, field="amount"):
    return (qs.aggregate(total=Sum(field))["total"] or ZERO).quantize(Decimal("0.01"))


def _confirmed_allocations(owner):
    return CostAllocation.objects.filter(line__purchase__owner=owner, line__purchase__status=Purchase.Status.CONFIRMED)


@dataclass
class ProjectCostSummary:
    opening: Decimal
    purchases: Decimal
    refunds: Decimal
    budget: Decimal | None

    @property
    def net(self):
        return self.opening + self.purchases - self.refunds

    @property
    def recorded(self):
        return self.purchases - self.refunds

    @property
    def budget_remaining(self):
        if self.budget is None:
            return None
        return self.budget - self.net

    @property
    def over_budget(self):
        return self.budget is not None and self.net > self.budget

    @property
    def over_by(self):
        """How far net cost exceeds the budget (None when there is no budget or it is not exceeded)."""
        return self.net - self.budget if self.over_budget else None

    @property
    def budget_percent(self):
        if not self.budget:
            return None
        return min(100, int(self.net / self.budget * 100)) if self.net > 0 else 0


def project_cost_summary(project):
    allocations = _confirmed_allocations(project.owner).filter(project=project)
    return ProjectCostSummary(
        opening=_sum(OpeningCostBalance.objects.filter(project=project)),
        purchases=_sum(allocations.filter(line__purchase__kind=Purchase.Kind.PURCHASE)),
        refunds=_sum(allocations.filter(line__purchase__kind=Purchase.Kind.REFUND)),
        budget=project.budget,
    )


def project_cost_summaries(owner, projects):
    """``ProjectCostSummary`` per project id for a list of the owner's projects, in two queries.

    Same rules as ``project_cost_summary``: opening balances plus confirmed purchase allocations minus
    confirmed refund allocations. Drafts never count."""
    opening = {p.pk: ZERO for p in projects}
    purchases = dict(opening)
    refunds = dict(opening)
    ids = list(opening)
    for row in OpeningCostBalance.objects.filter(project_id__in=ids).values("project_id").annotate(t=Sum("amount")):
        opening[row["project_id"]] += row["t"] or ZERO
    rows = (
        _confirmed_allocations(owner).filter(project_id__in=ids)
        .values("project_id", "line__purchase__kind").annotate(t=Sum("amount"))
    )
    for row in rows:
        target = refunds if row["line__purchase__kind"] == Purchase.Kind.REFUND else purchases
        target[row["project_id"]] += row["t"] or ZERO
    return {p.pk: ProjectCostSummary(opening=opening[p.pk], purchases=purchases[p.pk], refunds=refunds[p.pk],
                                     budget=p.budget) for p in projects}


def project_net_costs(owner, projects):
    """Net cost per project id for a list of projects (see ``project_cost_summaries``)."""
    return {pk: summary.net for pk, summary in project_cost_summaries(owner, projects).items()}


@dataclass
class OverallSummary:
    opening: Decimal
    projects: Decimal
    shared_tools: Decimal
    unallocated: Decimal

    @property
    def projects_with_opening(self):
        return self.opening + self.projects

    @property
    def total(self):
        return self.opening + self.projects + self.shared_tools + self.unallocated


def overall_summary(owner, *, project=None, merchant="", date_from=None, date_to=None):
    """Overall net recorded cost. Shared and unallocated amounts are counted once.

    Filters apply to purchases; opening balances are included only when no date
    or merchant filter is active (they have no merchant and cover a period).
    """
    allocations = _confirmed_allocations(owner)
    if project is not None:
        allocations = allocations.filter(project=project)
    if merchant:
        allocations = allocations.filter(line__purchase__merchant__iexact=merchant)
    if date_from:
        allocations = allocations.filter(line__purchase__transaction_date__gte=date_from)
    if date_to:
        allocations = allocations.filter(line__purchase__transaction_date__lte=date_to)

    def net(qs):
        return _sum(qs.filter(line__purchase__kind=Purchase.Kind.PURCHASE)) - _sum(
            qs.filter(line__purchase__kind=Purchase.Kind.REFUND)
        )

    if merchant or date_from or date_to:
        opening = ZERO
    else:
        balances = OpeningCostBalance.objects.filter(project__owner=owner)
        if project is not None:
            balances = balances.filter(project=project)
        opening = _sum(balances)
    return OverallSummary(
        opening=opening,
        projects=net(allocations.filter(destination=CostAllocation.Destination.PROJECT)),
        shared_tools=net(allocations.filter(destination=CostAllocation.Destination.SHARED_TOOLS)),
        unallocated=net(allocations.filter(destination=CostAllocation.Destination.UNALLOCATED)),
    )


def purchase_project_share(purchase, project):
    """Net amount of one purchase/refund allocated to ``project``."""
    return _sum(CostAllocation.objects.filter(line__purchase=purchase, project=project))


def filtered_purchases(owner, *, project=None, merchant="", date_from=None, date_to=None, include_void=True):
    qs = Purchase.objects.filter(owner=owner).select_related("original_purchase")
    if not include_void:
        qs = qs.filter(status=Purchase.Status.CONFIRMED)
    if project is not None:
        qs = qs.filter(Q(lines__allocations__project=project)).distinct()
    if merchant:
        qs = qs.filter(merchant__iexact=merchant)
    if date_from:
        qs = qs.filter(transaction_date__gte=date_from)
    if date_to:
        qs = qs.filter(transaction_date__lte=date_to)
    return qs
