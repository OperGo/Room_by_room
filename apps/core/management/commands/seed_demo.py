"""Seed a disposable demo account with fictional, clearly labelled sample data.

Idempotent: if the demo account already has data, nothing is changed unless
``--reset`` is passed. Only accounts flagged ``is_demo`` can ever be reset, so
the owner's real account is never touched.
"""

import datetime
import io
import secrets
from pathlib import Path
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image, ImageDraw

from apps.core.uploads import ValidatedUpload
from apps.costs import services as cost_services
from apps.costs.models import Purchase
from apps.costs.services import AllocationInput, LineInput, PurchaseInput
from apps.projects import services as project_services
from apps.projects.models import Project, Task
from apps.shopping.models import ShoppingItem

D = Decimal


ASSETS = Path(__file__).resolve().parents[2] / "seed_assets"


def sample_photo(name):
    """Sample imagery cropped from the approved generated mockups. Not a photograph of a real home."""
    import hashlib

    content = (ASSETS / name).read_bytes()
    with Image.open(io.BytesIO(content)) as im:
        w, h = im.size
    return ValidatedUpload(content=content, mime="image/jpeg", size=len(content),
                           checksum=hashlib.sha256(content).hexdigest(), width=w, height=h)


def sample_receipt_image():
    """A synthetic receipt, clearly marked as a sample. Contains no real data."""
    from PIL import ImageFont

    w, h = 900, 1500
    im = Image.new("RGB", (w, h), "#FFFFFF")
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.load_default(size=34)
        small = ImageFont.load_default(size=26)
    except TypeError:  # older Pillow
        font = small = ImageFont.load_default()
    y = 60
    d.text((w // 2, y), "SAMPLE HARDWARE CO", fill="#111", font=font, anchor="mt"); y += 60
    d.text((w // 2, y), "SAMPLE RECEIPT - NOT A REAL PURCHASE", fill="#555", font=small, anchor="mt"); y += 50
    d.text((w // 2, y), "26/09/2026  14:12", fill="#333", font=small, anchor="mt"); y += 80
    rows = [("Wood glue 500ml", "6.49"), ("Brad nails 30mm x2", "7.98"), ("Sanding sheets 120g", "8.50"),
            ("Paint tray", "4.25"), ("Delivery", "3.95")]
    for name, amount in rows:
        d.text((70, y), name, fill="#111", font=font); d.text((w - 70, y), amount, fill="#111", font=font, anchor="ra"); y += 64
    d.line([70, y, w - 70, y], fill="#999", width=3); y += 30
    d.text((70, y), "TOTAL GBP", fill="#111", font=font); d.text((w - 70, y), "31.17", fill="#111", font=font, anchor="ra"); y += 90
    d.text((w // 2, y), "Card payment  **** ****", fill="#555", font=small, anchor="mt")
    out = io.BytesIO()
    im.rotate(1.2, fillcolor="#F2F0EA", expand=False).save(out, format="JPEG", quality=85)
    content = out.getvalue()
    import hashlib

    return ValidatedUpload(content=content, mime="image/jpeg", size=len(content),
                           checksum=hashlib.sha256(content).hexdigest(), width=w, height=h)


class Command(BaseCommand):
    help = "Create or refresh the disposable demo account with fictional sample data."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password", default=None, help="Defaults to a random password printed once.")
        parser.add_argument("--reset", action="store_true", help="Delete and recreate the demo account's data.")

    def handle(self, username, password, reset, **options):
        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if user and not user.is_demo:
            raise CommandError(f"{username!r} is a real account; the seed command only manages demo accounts.")
        created_password = None
        if user is None:
            created_password = password or secrets.token_urlsafe(12)
            user = User.objects.create_user(username=username, password=created_password, is_demo=True)
        elif password:
            user.set_password(password)
            user.save(update_fields=["password"])
        if Project.objects.filter(owner=user).exists():
            if not reset:
                self.stdout.write("Demo data already present; nothing changed. Use --reset to recreate it.")
                return
            self._wipe(user)
        with transaction.atomic():
            self._seed(user)
        self.stdout.write(self.style.SUCCESS(f"Demo data created for {username!r}."))
        if created_password:
            self.stdout.write(f"Demo password (shown once): {created_password}")

    def _wipe(self, user):
        from apps.core.models import ChangeEvent
        from apps.core.storage import private_storage
        from apps.costs.models import CostAllocation, OpeningBalanceDecision, OpeningCostBalance, PurchaseEvidence, PurchaseLine
        from apps.receipts.models import ReceiptDocument, ReceiptDraft

        assert user.is_demo
        storage = private_storage()
        with transaction.atomic():
            from apps.projects.models import ProjectPhoto

            keys = list(ProjectPhoto.objects.filter(project__owner=user).values_list("storage_key", flat=True))
            keys += list(ReceiptDocument.objects.filter(owner=user).values_list("storage_key", flat=True))
            ShoppingItem.objects.filter(owner=user).delete()
            OpeningBalanceDecision.objects.filter(purchase__owner=user).delete()
            PurchaseEvidence.objects.filter(purchase__owner=user).delete()
            CostAllocation.objects.filter(line__purchase__owner=user).delete()
            PurchaseLine.objects.filter(purchase__owner=user).delete()
            Purchase.objects.filter(owner=user, kind=Purchase.Kind.REFUND).delete()
            Purchase.objects.filter(owner=user).delete()
            ReceiptDraft.objects.filter(owner=user).delete()
            ReceiptDocument.objects.filter(owner=user).delete()
            OpeningCostBalance.objects.filter(project__owner=user).delete()
            Project.objects.filter(owner=user).update(cover_photo=None)
            Project.objects.filter(owner=user).delete()
            ChangeEvent.objects.filter(owner=user).delete()
        for key in keys:
            storage.delete(key)

    def _seed(self, user):
        office = project_services.save_project(user, Project(
            title="Office cabinetry", room="Office", status=Project.Status.ACTIVE, budget=D("1200.00"),
            start_date=datetime.date(2026, 8, 15),
            notes="Built-in cabinets and shelving along the alcove wall. (Fictional demo project.)",
        ))
        hallway = project_services.save_project(user, Project(
            title="Hallway refresh", room="Hallway", status=Project.Status.ACTIVE, budget=D("400.00"),
            start_date=datetime.date(2026, 9, 1), notes="Fictional demo project.",
        ))
        bathroom = project_services.save_project(user, Project(
            title="Bathroom retile", room="Bathroom", status=Project.Status.COMPLETED, budget=D("900.00"),
            start_date=datetime.date(2025, 3, 1), completion_date=datetime.date(2025, 6, 20),
            notes="Older fictional project with an estimated opening balance.",
        ))
        project_services.save_project(user, Project(
            title="Garden shed shelving", room="Garden", status=Project.Status.PLANNED,
            notes="Fictional demo project with no tasks yet.",
        ))

        def task(project, title, minutes=None, status=None):
            t = project_services.save_task(user, Task(project=project, title=title, estimated_minutes=minutes))
            if status == "done":
                project_services.complete_task(user, t)
            return t

        office_titles = [
            ("Measure alcoves and walls", 45, "done"), ("Draw cabinet plan", 120, "done"),
            ("Buy MDF and hardware", 90, "done"), ("Cut carcass panels", 240, "done"),
            ("Assemble carcasses", 300, "done"), ("Fix carcasses to wall", 180, "done"),
            ("Fill and sand joints", 120, None), ("Prime cabinets", 150, None),
            ("Paint top coats", 240, None), ("Fit cable grommets in desk top", 30, None),
        ]
        office_tasks = [task(office, *row) for row in office_titles]
        project_services.set_dependencies(user, office_tasks[7], [office_tasks[6]])
        project_services.set_dependencies(user, office_tasks[8], [office_tasks[7]])
        hall = [task(hallway, "Fill ceiling cracks", 60), task(hallway, "Sand and prime ceiling", 90),
                task(hallway, "Paint walls", 300), task(hallway, "Replace skirting by front door", 120)]
        project_services.set_dependencies(user, hall[1], [hall[0]])
        project_services.set_dependencies(user, hall[2], [hall[1]])
        for title in ("Remove old tiles", "Tile walls", "Grout and seal"):
            task(bathroom, title, None, "done")

        project_services.add_photo(user, office, sample_photo("sample-office.jpg"),
                                   caption="Sample image (generated concept), not a real home", is_sample=True)
        project_services.add_photo(user, hallway, sample_photo("sample-hallway.jpg"),
                                   caption="Sample image (generated concept), not a real home", is_sample=True)

        cost_services.create_opening_balance(
            user, bathroom, amount=D("850.00"), coverage_through=datetime.date(2025, 6, 30),
            note="Estimate from old bank statements (fictional).",
        )

        def alloc(project_or_kind, amount):
            if isinstance(project_or_kind, Project):
                return AllocationInput("project", D(amount), project_or_kind)
            return AllocationInput(project_or_kind, D(amount))

        # The CTO brief fixture: £76.50 split across Office and Hallway.
        cost_services.post_purchase(user, PurchaseInput(
            description="MDF, filler and primer", merchant="Sample Timber Merchant",
            transaction_date=datetime.date(2026, 9, 12), total=D("76.50"), lines=[
                LineInput("18mm MDF sheet", D("32.00"), [alloc(office, "32.00")]),
                LineInput("Fine surface filler", D("9.50"), [alloc(hallway, "9.50")]),
                LineInput("Primer undercoat 2.5L", D("35.00"), [alloc(office, "35.00")]),
            ]))
        cost_services.post_purchase(user, PurchaseInput(
            description="Sanding block set", merchant="Sample Tool Shop",
            transaction_date=datetime.date(2026, 9, 14), total=D("20.00"), lines=[
                LineInput("Sanding block set", D("20.00"), [alloc("shared_tools", "20.00")], category="tool"),
            ]))
        cost_services.post_purchase(user, PurchaseInput(
            description="Soft-close hinges", merchant="Sample Hardware Co",
            transaction_date=datetime.date(2026, 9, 20), total=D("48.60"), lines=[
                LineInput("Soft-close hinges", D("54.00"), [alloc(office, "54.00")], quantity=D("10"), unit_price=D("5.40")),
                LineInput("Multi-buy discount", D("-5.40"), [alloc(office, "-5.40")], line_type="discount", category="other"),
            ]))

        from apps.receipts.services import store_receipt

        store_receipt(user, sample_receipt_image(), "sample-receipt.jpg")

        def item(description, quantity, unit="", project=None, task_obj=None, retailer="", bought=False):
            from django.utils import timezone

            ShoppingItem.objects.create(
                owner=user, description=description, quantity=D(quantity), unit=unit, project=project, task=task_obj,
                retailer=retailer, purchased_at=timezone.now() if bought else None,
            )

        item("Decorator's caulk", "2", "tubes", office, office_tasks[6], "Sample Hardware Co")
        item("Satin paint, 2.5L", "1", "tin", office, office_tasks[8], "Sample Paint Co")
        item("Cable grommets 60mm", "2", "", office, office_tasks[9], "Sample Hardware Co")
        item("Ceiling paint, 5L", "1", "tin", hallway, hall[1], "Sample Paint Co")
        item("Masking tape", "3", "rolls", None, None, "Sample Paint Co")
        item("Dust sheets", "2", "", None, None, "", bought=True)
