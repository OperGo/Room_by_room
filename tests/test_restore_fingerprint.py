"""The restore fingerprint (Sprint 2A closeout) detects lost or altered files and changed totals."""

import io
import json

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.core.storage import private_storage
from apps.receipts.models import ReceiptDocument

from .conftest import image_bytes, upload

pytestmark = pytest.mark.django_db


def _fingerprint():
    out = io.StringIO()
    call_command("restore_fingerprint", stdout=out)
    return json.loads(out.getvalue())


def test_fingerprint_reports_files_and_totals_without_private_content(client_owner, owner, office):
    client_owner.post(reverse("receipts:new"), {"receipt": upload("r.jpg", image_bytes())})
    document = ReceiptDocument.objects.get()
    result = _fingerprint()
    assert result["files"]["references"] == 1 and result["files"]["missing_references"] == 0
    assert result["files"]["receipt_checksum_mismatches"] == 0
    assert result["money"][f"owner-{owner.pk}"]["overall_total"] == "0.00"
    assert "r.jpg" not in json.dumps(result)  # no filenames or merchants in the output
    # A missing or altered file is visible in the fingerprint.
    storage = private_storage()
    storage.delete(document.storage_key)
    assert _fingerprint()["files"]["missing_references"] == 1
    storage.save(document.storage_key, io.BytesIO(b"altered"))
    assert _fingerprint()["files"]["receipt_checksum_mismatches"] == 1
