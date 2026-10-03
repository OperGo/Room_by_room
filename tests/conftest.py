import datetime
import io
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.costs.services import AllocationInput, LineInput, PurchaseInput
from apps.projects.models import Project

D = Decimal


@pytest.fixture(autouse=True)
def private_storage_tmp(settings, tmp_path):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.STORAGES = {
        **settings.STORAGES,
        "private": {"BACKEND": "apps.core.storage.PrivateFileSystemStorage", "OPTIONS": {"location": tmp_path / "private"}},
    }
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"
    return tmp_path / "private"


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="owner", password="correct-horse-battery")


@pytest.fixture
def intruder(django_user_model):
    return django_user_model.objects.create_user(username="intruder", password="correct-horse-battery")


@pytest.fixture
def client_owner(client, owner):
    client.force_login(owner)
    return client


@pytest.fixture
def office(owner):
    return Project.objects.create(owner=owner, title="Office", budget=D("1200.00"))


@pytest.fixture
def hallway(owner):
    return Project.objects.create(owner=owner, title="Hallway")


def to(project, amount):
    return AllocationInput("project", D(amount), project)


def shared(amount):
    return AllocationInput("shared_tools", D(amount))


def unallocated(amount):
    return AllocationInput("unallocated", D(amount))


def purchase_input(lines, total=None, date=datetime.date(2026, 9, 12), description="Test purchase", merchant="Test Merchant"):
    if total is None:
        total = sum((l.amount for l in lines), D("0.00"))
    return PurchaseInput(description=description, transaction_date=date, total=D(total), lines=lines, merchant=merchant)


def line(description, amount, allocations, **kwargs):
    return LineInput(description, D(amount), allocations, **kwargs)


def image_bytes(fmt="JPEG", size=(120, 80), color="white", exif_orientation=None):
    im = Image.new("RGB", size, color)
    out = io.BytesIO()
    kwargs = {}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kwargs["exif"] = exif
    im.save(out, format=fmt, **kwargs)
    return out.getvalue()


def upload(name, content, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, content, content_type=content_type)


def pdf_bytes(pages=1, password=None):
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=300)
    if password:
        writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
