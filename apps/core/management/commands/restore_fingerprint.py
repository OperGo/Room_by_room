"""Read-only fingerprint of the data a restore must preserve (Sprint 2A closeout).

Run against the source database and against a restored copy, then compare the two outputs:

    python manage.py restore_fingerprint > before.json
    DATABASE_URL=postgres://.../restored python manage.py restore_fingerprint > after.json
    diff before.json after.json

The output holds counts, SHA-256 digests and money totals only — no names, merchants or file bytes —
so it is safe to keep alongside restore evidence.
"""

import hashlib
import json

from django.apps import apps
from django.core.management.base import BaseCommand

from apps.core.models import StoredFile
from apps.core.storage import private_storage
from apps.costs.models import Purchase
from apps.costs.selectors import overall_summary, project_cost_summary
from apps.projects.models import Project, ProjectPhoto
from apps.receipts.models import ReceiptDocument


class Command(BaseCommand):
    help = "Print a JSON fingerprint (file digests, financial totals, row counts) for restore checks."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(fingerprint(), indent=2, sort_keys=True))


def fingerprint():
    files = hashlib.sha256()
    file_count = size_mismatches = 0
    for name, content, size in StoredFile.objects.order_by("name").values_list("name", "content", "size").iterator():
        data = bytes(content)
        file_count += 1
        size_mismatches += len(data) != size
        files.update(name.encode() + b"\0" + hashlib.sha256(data).digest())

    # Every stored file reference (receipt originals, HEIC previews, project photos) must resolve after a
    # restore, and each receipt original must still match the checksum recorded at upload.
    storage = private_storage()
    references = missing = checksum_mismatches = 0
    for document in ReceiptDocument.objects.order_by("pk"):
        for key in filter(None, (document.storage_key, document.preview_key)):
            references += 1
            if not storage.exists(key):
                missing += 1
            elif key == document.storage_key:
                with storage.open(key) as handle:
                    checksum_mismatches += hashlib.sha256(handle.read()).hexdigest() != document.checksum
    for key in ProjectPhoto.objects.order_by("pk").values_list("storage_key", flat=True):
        references += 1
        missing += not storage.exists(key)

    money = {}
    for owner_id in Project.objects.values_list("owner_id", flat=True).distinct().order_by("owner_id"):
        owner = Project.objects.filter(owner_id=owner_id).first().owner
        money[f"owner-{owner_id}"] = {
            "overall_total": str(overall_summary(owner).total),
            "projects": {str(p.uuid): str(project_cost_summary(p).net)
                         for p in Project.objects.filter(owner=owner).order_by("uuid")},
        }
    counts = {m._meta.label: m._default_manager.count() for m in apps.get_models()
              if m._meta.app_label in {"core", "projects", "costs", "receipts", "shopping"}}
    return {
        "files": {"count": file_count, "digest": files.hexdigest(), "size_mismatches": size_mismatches,
                  "references": references, "missing_references": missing,
                  "receipt_checksum_mismatches": checksum_mismatches},
        "money": money,
        "confirmed_purchases": Purchase.objects.filter(status=Purchase.Status.CONFIRMED).count(),
        "row_counts": counts,
    }
