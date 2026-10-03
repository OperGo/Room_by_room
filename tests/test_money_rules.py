"""Money rules from section 5 of the CTO brief, as acceptance tests."""

import datetime
from decimal import Decimal
from unittest import mock

import pytest
from django.db import IntegrityError, transaction

from apps.core.exceptions import BusinessRuleError, StaleObjectError
from apps.core.models import ChangeEvent
from apps.costs import services
from apps.costs.models import CostAllocation, OpeningCostBalance, Purchase, PurchaseLine
from apps.costs.selectors import overall_summary, project_cost_summary
from apps.projects.models import Project

from .conftest import line, purchase_input, shared, to, unallocated

D = Decimal
pytestmark = pytest.mark.django_db


def fixture_purchase(owner, office, hallway):
    return services.post_purchase(owner, purchase_input([
        line("MDF", "32.00", [to(office, "32.00")]),
        line("Filler", "9.50", [to(hallway, "9.50")]),
        line("Primer", "35.00", [to(office, "35.00")]),
    ], total="76.50"))


def test_brief_example_arithmetic(owner, office, hallway):
    purchase = fixture_purchase(owner, office, hallway)
    assert purchase.total == D("76.50")
    assert project_cost_summary(office).net == D("67.00")
    assert project_cost_summary(hallway).net == D("9.50")
    assert overall_summary(owner).total == D("76.50")

    services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 15),
                             amounts={f"project:{hallway.uuid}": D("9.50")})
    assert project_cost_summary(hallway).net == D("0.00")
    assert project_cost_summary(office).net == D("67.00")
    assert overall_summary(owner).total == D("67.00")

    services.post_purchase(owner, purchase_input([line("Sander", "20.00", [shared("20.00")], category="tool")]))
    assert overall_summary(owner).total == D("87.00")
    assert overall_summary(owner).shared_tools == D("20.00")
    assert project_cost_summary(office).net == D("67.00")
    assert project_cost_summary(hallway).net == D("0.00")


def test_total_must_reconcile_with_lines(owner, office):
    with pytest.raises(BusinessRuleError) as exc:
        services.post_purchase(owner, purchase_input([line("MDF", "32.00", [to(office, "32.00")])], total="40.00"))
    assert "Items add up to £32.00" in str(exc.value)
    assert Purchase.objects.count() == 0


def test_adjustment_lines_reconcile_shipping_discount_rounding(owner, office):
    p = services.post_purchase(owner, purchase_input([
        line("Hinges", "54.00", [to(office, "54.00")], quantity=D("10"), unit_price=D("5.40")),
        line("Delivery", "4.99", [to(office, "4.99")], line_type="shipping", category="other"),
        line("Discount", "-5.40", [to(office, "-5.40")], line_type="discount", category="other"),
        line("Rounding", "0.01", [to(office, "0.01")], line_type="rounding", category="other"),
    ], total="53.60"))
    assert p.total == D("53.60")
    assert project_cost_summary(office).net == D("53.60")


def test_unit_price_is_descriptive_only(owner, office):
    # OCR-style mismatch: 3 x 1.99 != 5.00. The line total is what counts.
    services.post_purchase(owner, purchase_input([
        line("Screws", "5.00", [to(office, "5.00")], quantity=D("3"), unit_price=D("1.99")),
    ]))
    assert project_cost_summary(office).net == D("5.00")


def test_discount_must_be_negative_and_items_non_negative(owner, office):
    with pytest.raises(BusinessRuleError):
        services.post_purchase(owner, purchase_input([
            line("Item", "10.00", [to(office, "10.00")]),
            line("Discount", "2.00", [to(office, "2.00")], line_type="discount"),
        ]))
    with pytest.raises(BusinessRuleError):
        services.post_purchase(owner, purchase_input([line("Item", "-1.00", [to(office, "-1.00")])], total="0.00"))
    assert Purchase.objects.count() == 0


def test_negative_purchase_total_rejected(owner, office):
    with pytest.raises(BusinessRuleError):
        services.post_purchase(owner, purchase_input([
            line("Item", "1.00", [to(office, "1.00")]),
            line("Discount", "-2.00", [to(office, "-2.00")], line_type="discount"),
        ], total="-1.00"))


def test_quantity_must_be_positive(owner, office):
    with pytest.raises(BusinessRuleError):
        services.post_purchase(owner, purchase_input([line("Item", "1.00", [to(office, "1.00")], quantity=D("0"))]))


def test_unitemised_purchase_line(owner, office):
    p = services.post_purchase(owner, purchase_input([
        line("Unitemised purchase", "112.40", [to(office, "112.40")], line_type="unitemised", category="other"),
    ]))
    assert p.lines.get().line_type == PurchaseLine.LineType.UNITEMISED


def test_allocations_must_equal_line_exactly(owner, office, hallway):
    with pytest.raises(BusinessRuleError) as exc:
        services.post_purchase(owner, purchase_input([
            line("Paint", "30.00", [to(office, "20.00"), to(hallway, "9.99")]),
        ]))
    assert "allocations add up to £29.99" in str(exc.value)


def test_split_across_projects_and_destinations(owner, office, hallway):
    services.post_purchase(owner, purchase_input([
        line("Paint", "30.00", [to(office, "20.00"), to(hallway, "7.00"), unallocated("3.00")]),
    ]))
    assert project_cost_summary(office).net == D("20.00")
    assert project_cost_summary(hallway).net == D("7.00")
    summary = overall_summary(owner)
    assert summary.unallocated == D("3.00")
    assert summary.total == D("30.00")


def test_shared_tool_not_counted_per_project(owner, office, hallway):
    services.post_purchase(owner, purchase_input([line("Drill", "89.00", [shared("89.00")], category="tool")]))
    assert project_cost_summary(office).net == D("0.00")
    assert project_cost_summary(hallway).net == D("0.00")
    assert overall_summary(owner).total == D("89.00")


def test_cross_owner_project_allocation_rejected(owner, intruder):
    theirs = Project.objects.create(owner=intruder, title="Not yours")
    with pytest.raises(BusinessRuleError):
        services.post_purchase(owner, purchase_input([line("Item", "5.00", [to(theirs, "5.00")])]))
    assert Purchase.objects.count() == 0


def test_discount_cannot_make_destination_negative(owner, office, hallway):
    with pytest.raises(BusinessRuleError):
        services.post_purchase(owner, purchase_input([
            line("Item", "10.00", [to(office, "10.00")]),
            line("Discount", "-2.00", [to(hallway, "-2.00")], line_type="discount"),
        ]))


# ------------------------------------------------------------------ refunds


def test_refund_caps_per_destination_and_cumulatively(owner, office, hallway):
    purchase = fixture_purchase(owner, office, hallway)
    key_h = f"project:{hallway.uuid}"
    key_o = f"project:{office.uuid}"
    with pytest.raises(BusinessRuleError):
        services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 13), amounts={key_h: D("9.51")})
    services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 13), amounts={key_h: D("5.00")})
    with pytest.raises(BusinessRuleError):
        services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 14), amounts={key_h: D("5.00")})
    services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 14), amounts={key_h: D("4.50"), key_o: D("10.00")})
    assert project_cost_summary(hallway).net == D("0.00")
    assert project_cost_summary(office).net == D("57.00")
    with pytest.raises(BusinessRuleError):
        services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 14),
                                 amounts={"shared_tools": D("1.00")})


def test_refund_is_positive_record_linked_to_original(owner, office, hallway):
    purchase = fixture_purchase(owner, office, hallway)
    refund = services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 13),
                                      amounts={f"project:{hallway.uuid}": D("9.50")})
    assert refund.kind == Purchase.Kind.REFUND and refund.total == D("9.50") and refund.original_purchase == purchase
    with pytest.raises(BusinessRuleError):
        services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 13),
                                 amounts={f"project:{office.uuid}": D("-1.00")})
    with pytest.raises(BusinessRuleError):
        services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 1),
                                 amounts={f"project:{office.uuid}": D("1.00")})


# ------------------------------------------------------------------ void, correction, history


def test_void_excludes_from_totals_and_keeps_record(owner, office, hallway):
    purchase = fixture_purchase(owner, office, hallway)
    with pytest.raises(BusinessRuleError):
        services.void_purchase(owner, purchase, purchase.version, "")
    services.void_purchase(owner, purchase, purchase.version, "Entered twice")
    purchase.refresh_from_db()
    assert purchase.status == Purchase.Status.VOID and purchase.void_reason == "Entered twice"
    assert overall_summary(owner).total == D("0.00")
    assert ChangeEvent.objects.filter(subject_id=str(purchase.uuid), action="voided").exists()


def test_void_blocked_while_refunds_confirmed(owner, office, hallway):
    purchase = fixture_purchase(owner, office, hallway)
    refund = services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 13),
                                      amounts={f"project:{hallway.uuid}": D("9.50")})
    with pytest.raises(BusinessRuleError):
        services.void_purchase(owner, purchase, purchase.version, "wrong")
    services.void_purchase(owner, refund, refund.version, "refund recorded in error")
    assert project_cost_summary(hallway).net == D("9.50")
    purchase.refresh_from_db()
    services.void_purchase(owner, purchase, purchase.version, "wrong")
    assert overall_summary(owner).total == D("0.00")


def test_correction_replaces_lines_and_records_history(owner, office, hallway):
    purchase = fixture_purchase(owner, office, hallway)
    corrected = services.correct_purchase(owner, purchase, purchase.version, purchase_input([
        line("MDF", "32.00", [to(office, "32.00")]),
        line("Filler", "9.50", [to(office, "9.50")]),
        line("Primer", "35.00", [to(office, "35.00")]),
    ]), reason="Filler was for the office")
    assert corrected.version == 2
    assert project_cost_summary(office).net == D("76.50")
    assert project_cost_summary(hallway).net == D("0.00")
    event = ChangeEvent.objects.get(subject_id=str(purchase.uuid), action="corrected")
    assert event.reason == "Filler was for the office"
    assert event.before["lines"][1]["allocations"][0]["to"] == "Hallway"


def test_correction_requires_reason_and_current_version(owner, office, hallway):
    purchase = fixture_purchase(owner, office, hallway)
    data = purchase_input([line("MDF", "76.50", [to(office, "76.50")])])
    with pytest.raises(BusinessRuleError):
        services.correct_purchase(owner, purchase, purchase.version, data, reason=" ")
    with pytest.raises(StaleObjectError):
        services.correct_purchase(owner, purchase, purchase.version + 1, data, reason="typo")
    assert project_cost_summary(hallway).net == D("9.50")


def test_correction_cannot_undercut_recorded_refunds(owner, office, hallway):
    purchase = fixture_purchase(owner, office, hallway)
    services.refund_purchase(owner, purchase, transaction_date=datetime.date(2026, 9, 13),
                             amounts={f"project:{hallway.uuid}": D("9.50")})
    purchase.refresh_from_db()
    with pytest.raises(BusinessRuleError):
        services.correct_purchase(owner, purchase, purchase.version,
                                  purchase_input([line("All office", "76.50", [to(office, "76.50")])]), reason="x")


def test_failed_post_leaves_zero_cost(owner, office):
    """An error after rows are written rolls the whole purchase back."""
    with mock.patch("apps.costs.services.record_change", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            services.post_purchase(owner, purchase_input([line("MDF", "32.00", [to(office, "32.00")])]))
    assert Purchase.objects.count() == 0
    assert PurchaseLine.objects.count() == 0
    assert CostAllocation.objects.count() == 0
    assert overall_summary(owner).total == D("0.00")


def test_submission_key_makes_post_idempotent(owner, office):
    import uuid

    key = uuid.uuid4()
    data = purchase_input([line("MDF", "32.00", [to(office, "32.00")])])
    first = services.post_purchase(owner, data, submission_key=key)
    second = services.post_purchase(owner, data, submission_key=key)
    assert first.pk == second.pk
    assert Purchase.objects.count() == 1


def test_database_constraints_guard_invariants(owner, office):
    p = services.post_purchase(owner, purchase_input([line("MDF", "32.00", [to(office, "32.00")])]))
    with pytest.raises(IntegrityError), transaction.atomic():
        Purchase.objects.filter(pk=p.pk).update(total=D("-1.00"))
    with pytest.raises(IntegrityError), transaction.atomic():
        Purchase.objects.filter(pk=p.pk).update(currency="EUR")
    with pytest.raises(IntegrityError), transaction.atomic():
        Purchase.objects.filter(pk=p.pk).update(status="void")  # void without a reason
    with pytest.raises(IntegrityError), transaction.atomic():
        CostAllocation.objects.filter(line__purchase=p).update(destination="shared_tools")  # project still set


# ------------------------------------------------------------------ budgets


def test_budget_arithmetic_including_zero_and_over_budget(owner, office, hallway):
    hallway.budget = D("0.00")
    hallway.save()
    fixture_purchase(owner, office, hallway)
    office_summary = project_cost_summary(office)
    assert office_summary.budget_remaining == D("1133.00")
    hall = project_cost_summary(hallway)
    assert hall.budget_remaining == D("-9.50") and hall.over_budget
    assert hall.budget_percent is None  # zero budget: no division
    no_budget = Project.objects.create(owner=owner, title="No budget")
    assert project_cost_summary(no_budget).budget_remaining is None


# ------------------------------------------------------------------ opening balances


@pytest.fixture
def balance(owner, office):
    return services.create_opening_balance(owner, office, amount=D("500.00"),
                                           coverage_through=datetime.date(2026, 8, 31), note="Estimate")


def test_opening_balance_counts_once_in_project_and_overall(owner, office, balance):
    assert project_cost_summary(office).net == D("500.00")
    assert overall_summary(owner).total == D("500.00")
    with pytest.raises(BusinessRuleError):
        services.create_opening_balance(owner, office, amount=D("-1.00"), coverage_through=datetime.date(2026, 1, 1))


def test_purchase_in_covered_period_requires_decision(owner, office, balance):
    data = purchase_input([line("Old hinges", "40.00", [to(office, "40.00")])], date=datetime.date(2026, 8, 20))
    with pytest.raises(BusinessRuleError) as exc:
        services.post_purchase(owner, data)
    assert "opening balance" in str(exc.value)
    assert Purchase.objects.count() == 0
    # Outside the period: no decision needed.
    services.post_purchase(owner, purchase_input([line("New", "1.00", [to(office, "1.00")])], date=datetime.date(2026, 9, 1)))


def test_additional_spending_keeps_balance(owner, office, balance):
    data = purchase_input([line("Old hinges", "40.00", [to(office, "40.00")])], date=datetime.date(2026, 8, 20))
    p = services.post_purchase(owner, data, balance_choices=[services.BalanceChoice(str(balance.uuid), "additional")])
    balance.refresh_from_db()
    assert balance.amount == D("500.00")
    assert project_cost_summary(office).net == D("540.00")
    assert p.balance_decisions.get().decision == "additional"


def test_replacement_reduces_balance_in_same_transaction(owner, office, balance):
    data = purchase_input([line("Old hinges", "40.00", [to(office, "40.00")])], date=datetime.date(2026, 8, 20))
    services.post_purchase(owner, data, balance_choices=[services.BalanceChoice(str(balance.uuid), "replace", D("40.00"))])
    balance.refresh_from_db()
    assert balance.amount == D("460.00") and balance.original_amount == D("500.00")
    assert project_cost_summary(office).net == D("500.00")  # not double counted


def test_replacement_cannot_exceed_balance_or_purchase(owner, office, balance):
    big = purchase_input([line("Kitchen", "600.00", [to(office, "600.00")])], date=datetime.date(2026, 8, 20))
    with pytest.raises(BusinessRuleError):
        services.post_purchase(owner, big, balance_choices=[services.BalanceChoice(str(balance.uuid), "replace", D("600.00"))])
    small = purchase_input([line("Hinge", "10.00", [to(office, "10.00")])], date=datetime.date(2026, 8, 20))
    with pytest.raises(BusinessRuleError):
        services.post_purchase(owner, small, balance_choices=[services.BalanceChoice(str(balance.uuid), "replace", D("20.00"))])
    balance.refresh_from_db()
    assert balance.amount == D("500.00")
    assert Purchase.objects.count() == 0


def test_void_reverses_replacement(owner, office, balance):
    data = purchase_input([line("Old hinges", "40.00", [to(office, "40.00")])], date=datetime.date(2026, 8, 20))
    p = services.post_purchase(owner, data, balance_choices=[services.BalanceChoice(str(balance.uuid), "replace", D("40.00"))])
    services.void_purchase(owner, p, p.version, "Duplicate")
    balance.refresh_from_db()
    assert balance.amount == D("500.00")
    assert project_cost_summary(office).net == D("500.00")


def test_opening_balance_edit_cannot_go_below_replaced(owner, office, balance):
    data = purchase_input([line("Old hinges", "40.00", [to(office, "40.00")])], date=datetime.date(2026, 8, 20))
    services.post_purchase(owner, data, balance_choices=[services.BalanceChoice(str(balance.uuid), "replace", D("40.00"))])
    balance.refresh_from_db()
    with pytest.raises(BusinessRuleError):
        services.update_opening_balance(owner, balance, balance.version, amount=D("30.00"),
                                        coverage_through=balance.coverage_through, note="", reason="lower")
    updated = services.update_opening_balance(owner, balance, balance.version, amount=D("300.00"),
                                              coverage_through=balance.coverage_through, note="", reason="Found statements")
    assert updated.amount == D("260.00")
    with pytest.raises(StaleObjectError):
        services.update_opening_balance(owner, balance, balance.version, amount=D("300.00"),
                                        coverage_through=balance.coverage_through, note="", reason="again")


def test_opening_balance_not_negative_in_db(owner, office, balance):
    with pytest.raises(IntegrityError), transaction.atomic():
        OpeningCostBalance.objects.filter(pk=balance.pk).update(amount=D("-1.00"))


def test_project_archive_and_task_cancel_keep_costs(owner, office, hallway):
    from apps.projects import services as ps
    from apps.projects.models import Task

    fixture_purchase(owner, office, hallway)
    t = ps.save_task(owner, Task(project=office, title="Paint"))
    ps.set_task_status(owner, t, "cancelled")
    ps.set_project_status(owner, office, "archived")
    assert project_cost_summary(office).net == D("67.00")
    assert overall_summary(owner).total == D("76.50")
