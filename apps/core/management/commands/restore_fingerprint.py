"""Read-only fingerprint of the data a restore must preserve (Sprint 2A closeout).

Run against the source database and against a restored copy, then compare the two outputs:

    python manage.py restore_fingerprint > before.json
    DATABASE_URL=postgres://.../restored python manage.py restore_fingerprint > after.json
    diff before.json after.json

The output holds counts, SHA-256 digests and money totals only — no names, merchants or file bytes —
so it is safe to keep alongside restore evidence.

On Render (recovery drill) the restored database is named by a private environment variable, so its URL
never appears in a command or a log:

    python manage.py restore_fingerprint --database-url-env RESTORE_DATABASE_URL

With that option every query and file check runs against the selected database, read-only; the normal
``DATABASE_URL`` configuration is left untouched. Missing or invalid settings fail without checking anything.
"""

import contextlib
import hashlib
import json
import os
from urllib.parse import urlparse

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connections, router

from apps.core.models import StoredFile
from apps.core.storage import DatabaseStorage, private_storage
from apps.costs.models import Purchase
from apps.costs.selectors import overall_summary, project_cost_summary
from apps.projects.models import Project, ProjectPhoto
from apps.receipts.models import ReceiptDocument


RESTORE_ALIAS = "restore_check"


class _OnlyRestoredDatabase:
    """Database router used for the duration of a ``--database-url-env`` run: every read, and any attempted
    write, goes to the selected database, never to the source configured by ``DATABASE_URL``."""

    def db_for_read(self, model, **hints):
        return RESTORE_ALIAS

    def db_for_write(self, model, **hints):
        return RESTORE_ALIAS

    def allow_relation(self, obj1, obj2, **hints):
        return True


def _selected_database(env_name):
    """Connection settings for the database named by ``env_name``. Never echoes the value."""
    value = (os.environ.get(env_name) or "").strip()
    if not value:
        raise CommandError(f"{env_name} is not set or is empty. Nothing was checked.")
    parsed = urlparse(value)
    if parsed.scheme in {"postgres", "postgresql"}:
        if not parsed.hostname or not parsed.path.strip("/"):
            raise CommandError(f"{env_name} must be a PostgreSQL URL with a host and database name. Nothing was checked.")
        from config.settings import database_from_url

        config = database_from_url(value)
        # Read-only at the database level as well: any write in this session is refused by PostgreSQL.
        config["OPTIONS"] = {"options": "-c default_transaction_read_only=on"}
    elif parsed.scheme == "sqlite" and parsed.path:
        config = {"ENGINE": "django.db.backends.sqlite3", "NAME": parsed.path}
    else:
        raise CommandError(f"{env_name} is not a supported database URL. Nothing was checked.")
    config["CONN_MAX_AGE"] = 0
    source = connections["default"].settings_dict
    same = (config["ENGINE"] == source["ENGINE"] and str(config["NAME"]) == str(source["NAME"])
            and config.get("HOST", "") == source.get("HOST", "") and str(config.get("PORT", "")) == str(source.get("PORT", "")))
    if same:
        raise CommandError(f"{env_name} names the source database itself. Nothing was checked.")
    return config


@contextlib.contextmanager
def _use_database(config):
    # configure_settings fills Django's defaults; it requires a "default" entry, which it leaves unchanged.
    configured = connections.configure_settings({"default": connections.settings["default"], RESTORE_ALIAS: config})
    connections.settings[RESTORE_ALIAS] = configured[RESTORE_ALIAS]
    guard = _OnlyRestoredDatabase()
    router.routers.insert(0, guard)
    try:
        yield
    finally:
        router.routers.remove(guard)
        if RESTORE_ALIAS in connections:
            connections[RESTORE_ALIAS].close()
            del connections[RESTORE_ALIAS]
        connections.settings.pop(RESTORE_ALIAS, None)


class Command(BaseCommand):
    help = "Print a JSON fingerprint (file digests, financial totals, row counts) for restore checks."

    def add_arguments(self, parser):
        parser.add_argument("--database-url-env", metavar="NAME",
                            help="Fingerprint the database whose URL is in this environment variable "
                                 "(for example a restored copy) instead of DATABASE_URL.")

    def handle(self, *args, database_url_env=None, **options):
        if not database_url_env:
            self.stdout.write(json.dumps(fingerprint(), indent=2, sort_keys=True))
            return
        config = _selected_database(database_url_env)
        with _use_database(config):
            try:
                # Files live in StoredFile rows; read them through the selected database, whatever storage
                # backend this process is configured with.
                result = fingerprint(storage=DatabaseStorage())
            except DatabaseError as exc:
                # Driver messages can include host, user or URL details: report only the error type.
                raise CommandError(f"Could not read the database named by {database_url_env} "
                                   f"({type(exc).__name__}). Nothing was compared.") from None
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))


def fingerprint(storage=None):
    files = hashlib.sha256()
    file_count = size_mismatches = 0
    for name, content, size in StoredFile.objects.order_by("name").values_list("name", "content", "size").iterator():
        data = bytes(content)
        file_count += 1
        size_mismatches += len(data) != size
        files.update(name.encode() + b"\0" + hashlib.sha256(data).digest())

    # Every stored file reference (receipt originals, HEIC previews, project photos) must resolve after a
    # restore, and each receipt original must still match the checksum recorded at upload.
    storage = storage or private_storage()
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
