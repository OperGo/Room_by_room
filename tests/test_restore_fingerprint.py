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


# ------------------------------------------------------------------ --database-url-env (recovery drill, route A)
#
# The restored copy is a separate database, so these run the command as a real process (as on Render) against
# two SQLite files: a "source" (DATABASE_URL) and a "restored" copy (RESTORE_DATABASE_URL) with different data.

import os  # noqa: E402
import shutil  # noqa: E402
import sqlite3  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from django.core.management.base import CommandError  # noqa: E402
from django.db import connections  # noqa: E402

from apps.core.management.commands.restore_fingerprint import RESTORE_ALIAS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
POPULATE = """
import hashlib
from django.contrib.auth import get_user_model
from apps.core.models import StoredFile
from apps.projects.models import Project
from apps.receipts.models import ReceiptDocument
user = get_user_model().objects.create_user("{who}", password="x-unused-123")
for n in range({projects}):
    Project.objects.create(owner=user, title=f"Room {{n}}")
content = b"{who} receipt bytes"
StoredFile.objects.create(name="receipts/{who}.jpg", content=content, size=len(content))
ReceiptDocument.objects.create(owner=user, storage_key="receipts/{who}.jpg", mime="image/jpeg", size=len(content),
                               checksum=hashlib.sha256(content).hexdigest())
"""


def _env(source, **extra):
    env = {k: v for k, v in os.environ.items() if k not in {"RESTORE_DATABASE_URL", "DATABASE_URL"}}
    env.update(DJANGO_SETTINGS_MODULE="config.settings", DJANGO_SECRET_KEY="fictional-test-secret",
               PRIVATE_STORAGE_BACKEND="database", DATABASE_URL=f"sqlite:///{source}", **extra)
    return env


def _manage(env, *args):
    return subprocess.run([sys.executable, "manage.py", *args], cwd=ROOT, env=env, capture_output=True, text=True)


@pytest.fixture(scope="module")
def databases(tmp_path_factory):
    base = tmp_path_factory.mktemp("restore")
    made = {}
    for who, projects in (("source", 3), ("restored", 1)):
        path = base / f"{who}.sqlite3"
        env = _env(path)
        assert _manage(env, "migrate", "-v0").returncode == 0
        done = _manage(env, "shell", "-c", POPULATE.format(who=who, projects=projects))
        assert done.returncode == 0, done.stderr
        made[who] = path
    return made


def _fp(source, restored=None):
    env = _env(source) if restored is None else _env(source, RESTORE_DATABASE_URL=f"sqlite:///{restored}")
    args = ["restore_fingerprint"] + ([] if restored is None else ["--database-url-env", "RESTORE_DATABASE_URL"])
    done = _manage(env, *args)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_selected_database_is_checked_and_the_source_is_untouched(databases):
    source_before = _fp(databases["source"])
    result = _fp(databases["source"], databases["restored"])
    # Every query and file check ran against the restored copy, not the source.
    assert result["row_counts"]["projects.Project"] == 1 and source_before["row_counts"]["projects.Project"] == 3
    assert result["files"]["count"] == 1 and result["files"]["references"] == 1
    assert result["files"]["missing_references"] == 0 == result["files"]["receipt_checksum_mismatches"]
    assert result["files"]["size_mismatches"] == 0
    assert result["files"]["digest"] != source_before["files"]["digest"]
    assert result == _fp(databases["restored"])  # identical to checking the copy directly
    assert _fp(databases["source"]) == source_before  # the source is unchanged


def test_restored_copy_with_lost_or_altered_file_is_detected(databases, tmp_path):
    copy = tmp_path / "tampered.sqlite3"
    shutil.copy(databases["restored"], copy)
    with sqlite3.connect(copy) as db:
        db.execute("UPDATE core_storedfile SET content = ? WHERE name = ?", (b"tampered", "receipts/restored.jpg"))
    files = _fp(databases["source"], copy)["files"]
    assert files["receipt_checksum_mismatches"] == 1 and files["size_mismatches"] == 1
    with sqlite3.connect(copy) as db:
        db.execute("DELETE FROM core_storedfile")
    assert _fp(databases["source"], copy)["files"]["missing_references"] == 1


def test_connection_failure_never_prints_credentials(databases):
    env = _env(databases["source"], RESTORE_DATABASE_URL="postgres://alice:S3cretPW@127.0.0.1:9/restored")
    done = _manage(env, "restore_fingerprint", "--database-url-env", "RESTORE_DATABASE_URL")
    assert done.returncode != 0 and done.stdout == ""
    assert "Could not read the database named by RESTORE_DATABASE_URL (OperationalError)" in done.stderr
    for secret in ("S3cretPW", "alice", "127.0.0.1", "postgres://", "Traceback"):
        assert secret not in done.stderr


def test_pointing_at_the_source_database_is_refused(databases):
    env = _env(databases["source"], RESTORE_DATABASE_URL=f"sqlite:///{databases['source']}")
    done = _manage(env, "restore_fingerprint", "--database-url-env", "RESTORE_DATABASE_URL")
    assert done.returncode != 0 and done.stdout == ""
    assert "names the source database itself. Nothing was checked." in done.stderr


@pytest.mark.parametrize("value", [None, "", "   ", "sqlite://", "mysql://alice:S3cretPW@db.example/rbr",
                                   "postgres://alice:S3cretPW@/rbr", "postgres://alice:S3cretPW@db.example/"])
def test_missing_or_invalid_configuration_checks_nothing(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("RESTORE_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("RESTORE_DATABASE_URL", value)
    out = io.StringIO()
    with pytest.raises(CommandError) as excinfo:
        call_command("restore_fingerprint", "--database-url-env", "RESTORE_DATABASE_URL", stdout=out)
    message = str(excinfo.value)
    assert "Nothing was checked." in message and "S3cretPW" not in message and "alice" not in message
    assert out.getvalue() == ""  # no fingerprint of the source was printed instead
    assert RESTORE_ALIAS not in connections.settings
