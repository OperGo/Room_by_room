"""Receipt review: "Unsaved changes" indicator and leave warning (CTO plan, 7 October).

The page marks itself; the browser behaviour is covered in tests/browser/test_unsaved_edits.py. Nothing about
the edits is stored in the browser, and saving, confirming and conflict recovery are unchanged.
"""
import re
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.urls import reverse

from apps.costs.models import Purchase
from apps.receipts.models import ReceiptDraft

from .conftest import image_bytes, upload

pytestmark = pytest.mark.django_db


def new_draft(client):
    client.post(reverse("receipts:new"), {"receipt": upload("r.jpg", image_bytes())})
    return ReceiptDraft.objects.latest("pk")


def editor_post(draft, version=None, total="10.00", amount="10.00", dest=""):
    return {"version": str(draft.version if version is None else version), "merchant": "Hardware Co",
            "transaction_date": "2026-09-26", "total": total,
            "line-0-description": "Screws", "line-0-amount": amount, "line-0-line_type": "item",
            "line-0-category": "material", "line-0-alloc-0-dest": dest, "line-0-alloc-0-amount": ""}


def editor_form_tag(html):
    return re.search(r"<form[^>]*data-editor-form[^>]*>", html).group(0)


def test_fresh_review_page_warns_only_after_edits(client_owner):
    draft = new_draft(client_owner)
    html = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    tag = editor_form_tag(html)
    assert "data-warn-unsaved" in tag and "data-dirty-on-load" not in tag
    assert html.count("data-unsaved-indicator hidden") == 2  # header badge and beside Save draft
    assert 'role="status" data-unsaved-live' in html


def test_refused_confirmation_returns_values_as_unsaved(client_owner, office):
    draft = new_draft(client_owner)
    response = client_owner.post(reverse("receipts:confirm", args=[draft.uuid]),
                                 editor_post(draft, total="12.00", dest=f"project:{office.uuid}"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "data-dirty-on-load" in editor_form_tag(html)  # the indicator shows at once
    assert 'value="Hardware Co"' in html
    assert Purchase.objects.count() == 0


def test_saved_draft_reopens_clean(client_owner):
    draft = new_draft(client_owner)
    response = client_owner.post(reverse("receipts:save", args=[draft.uuid]), editor_post(draft), follow=True)
    html = response.content.decode()
    assert "Draft saved." in html
    assert "data-dirty-on-load" not in editor_form_tag(html)


def test_stale_save_keeps_values_unsaved_and_reload_link_warns(client_owner):
    draft = new_draft(client_owner)
    response = client_owner.post(reverse("receipts:save", args=[draft.uuid]), editor_post(draft, version=draft.version - 1))
    html = response.content.decode()
    assert "Not saved yet" in html
    assert "data-dirty-on-load" in editor_form_tag(html)
    assert 'data-leave-message="Reload the stored draft? This discards the changes shown here."' in html


def test_manual_purchase_form_is_unchanged(client_owner):
    html = client_owner.get(reverse("costs:purchase_create")).content.decode()
    assert "data-warn-unsaved" not in html and "data-unsaved-indicator" not in html


def test_no_receipt_contents_kept_in_browser_storage():
    script = (Path(django_settings.BASE_DIR) / "static" / "js" / "app.js").read_text()
    for api in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"):
        assert api not in script
