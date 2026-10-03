"""Private files stored in PostgreSQL (the Render configuration): same behaviour as local files."""

import pytest
from django.urls import reverse

from apps.core.models import StoredFile
from apps.core.storage import private_storage
from apps.projects.models import Project, ProjectPhoto

from .conftest import image_bytes, pdf_bytes, upload

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def database_storage(settings):
    settings.STORAGES = {**settings.STORAGES, "private": {"BACKEND": "apps.core.storage.DatabaseStorage"}}


def test_receipt_upload_download_and_reading_input(client_owner, owner):
    from apps.receipts.extraction import _document_block
    from apps.receipts.models import ReceiptDocument

    client_owner.post(reverse("receipts:new"), {"receipt": upload("r.pdf", pdf_bytes(2))})
    document = ReceiptDocument.objects.get()
    assert StoredFile.objects.filter(name=document.storage_key).exists()
    response = client_owner.get(reverse("receipts:file", args=[document.uuid]))
    assert response.status_code == 200 and b"".join(response.streaming_content).startswith(b"%PDF-")
    assert _document_block(document)["type"] == "document"
    with pytest.raises(NotImplementedError):
        private_storage().url(document.storage_key)


def test_heic_preview_and_photo_lifecycle(client_owner, owner):
    from apps.receipts.models import ReceiptDocument

    client_owner.post(reverse("receipts:new"), {"receipt": upload("r.heic", image_bytes("HEIF"))})
    document = ReceiptDocument.objects.get()
    assert private_storage().exists(document.preview_key)
    project = Project.objects.create(owner=owner, title="Office")
    client_owner.post(reverse("projects:photo_upload", args=[project.uuid]), {"photo": upload("p.jpg", image_bytes())})
    photo = ProjectPhoto.objects.get()
    assert client_owner.get(reverse("projects:photo_file", args=[photo.uuid]))["Content-Type"] == "image/jpeg"
    client_owner.post(reverse("projects:photo_delete", args=[photo.uuid]))
    assert not StoredFile.objects.filter(name=photo.storage_key).exists()


def test_other_owner_cannot_download(client, owner, intruder):
    from apps.receipts.models import ReceiptDocument
    from apps.receipts.services import store_receipt
    from apps.core.uploads import validate_receipt

    document, _ = store_receipt(owner, validate_receipt(upload("r.jpg", image_bytes())), "r.jpg")
    client.force_login(intruder)
    assert client.get(reverse("receipts:file", args=[document.uuid])).status_code == 404
    assert ReceiptDocument.objects.count() == 1


def test_names_do_not_collide_and_listdir():
    from django.core.files.base import ContentFile

    storage = private_storage()
    a = storage.save("receipts/1/x.jpg", ContentFile(b"one"))
    b = storage.save("receipts/1/x.jpg", ContentFile(b"two"))
    assert a != b and storage.size(a) == 3
    assert storage.open(b).read() == b"two"
    dirs, files = storage.listdir("receipts")
    assert dirs == ["1"] and files == []
