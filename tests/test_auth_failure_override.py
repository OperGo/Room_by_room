"""Controlled authentication-failure check, proven locally.

The Milestone 2 negative test overrides the API key for one worker process only:
``env ANTHROPIC_API_KEY=invalid-pilot-test-key python manage.py process_receipts --once``.
Here the real Anthropic SDK runs against a local stub that answers 401, so no provider is called.
"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.costs.models import Purchase
from apps.receipts import jobs
from apps.receipts.models import ExtractionJob, ReceiptDraft

from .conftest import image_bytes, upload

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parent.parent
INVALID_KEY = "invalid-pilot-test-key"


class _Reject401(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        type(self).seen.append((self.path, self.headers.get("x-api-key")))
        body = json.dumps({"type": "error", "error": {"type": "authentication_error",
                                                      "message": "invalid x-api-key"}}).encode()
        self.send_response(401)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def stub_provider(monkeypatch):
    _Reject401.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Reject401)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", url)
    yield url
    server.shutdown()


@pytest.fixture
def draft(client_owner, owner):
    client_owner.post(reverse("receipts:new"), {"receipt": upload("r.jpg", image_bytes())})
    return ReceiptDraft.objects.get(owner=owner)


def test_invalid_key_fails_once_without_retry_and_keeps_manual_entry(stub_provider, settings, client_owner,
                                                                     owner, draft):
    settings.RECEIPT_EXTRACTOR = "anthropic"
    settings.RECEIPT_MODEL = "claude-haiku-4-5-20251001"
    settings.ANTHROPIC_API_KEY = INVALID_KEY
    assert os.environ["ANTHROPIC_BASE_URL"].startswith("http://127.0.0.1:")  # never the real provider
    jobs.request_reading(owner, draft, draft.version)

    call_command("process_receipts", "--once")
    call_command("process_receipts", "--once")  # a later run must not retry it

    job = ExtractionJob.objects.get()
    assert (job.status, job.attempts, job.error_code) == ("failed", 1, "auth")
    assert _Reject401.seen == [("/v1/messages", INVALID_KEY)]
    page = client_owner.get(reverse("receipts:review", args=[draft.uuid])).content.decode()
    assert "Couldn’t read this receipt" in page and "Confirm purchase" in page
    assert Purchase.objects.count() == 0


def test_env_prefix_overrides_the_key_for_that_process_only(stub_provider):
    """The production command prefix changes the key seen by the worker process, not its parent."""
    code = "from django.conf import settings; print(settings.ANTHROPIC_API_KEY)"
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", "ANTHROPIC_API_KEY": "stored-key",
           "DJANGO_SECRET_KEY": "fictional-test-secret"}
    run = lambda *prefix: subprocess.run([*prefix, sys.executable, "-c", f"import django; django.setup(); {code}"],
                                         cwd=ROOT, env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert run("env", f"ANTHROPIC_API_KEY={INVALID_KEY}") == INVALID_KEY
    assert run() == "stored-key"
