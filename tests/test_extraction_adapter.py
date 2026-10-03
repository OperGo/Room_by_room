"""Anthropic adapter with a mocked client: request shape, error mapping, no paid calls."""

import base64
import io
import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from PIL import Image

from apps.core.uploads import validate_receipt
from apps.receipts.extraction import (
    RECEIPT_SCHEMA, SAMPLE_RESULT, AnthropicExtractor, ExtractionError, extraction_status, get_extractor,
)
from apps.receipts.services import store_receipt

from .conftest import image_bytes, pdf_bytes, upload

pytestmark = pytest.mark.django_db
REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


class FakeMessages:
    def __init__(self, outcome):
        self.outcome = outcome
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def response(text=None, stop_reason="end_turn", model="claude-haiku-4-5-20251001"):
    text = json.dumps(SAMPLE_RESULT) if text is None else text
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop_reason, model=model,
                           usage=SimpleNamespace(input_tokens=1500, output_tokens=300), _request_id="req_test")


def extractor_with(outcome):
    messages = FakeMessages(outcome)
    client = SimpleNamespace(messages=messages)
    return AnthropicExtractor(api_key="test-key", model="claude-haiku-4-5", client=client), messages


@pytest.fixture
def jpeg_document(owner):
    big = io.BytesIO()
    Image.new("RGB", (3000, 4000), "white").save(big, format="JPEG")
    document, _ = store_receipt(owner, validate_receipt(upload("r.jpg", big.getvalue())), "r.jpg")
    return document


def test_request_shape_uses_structured_output_and_bounded_image(jpeg_document, settings):
    extractor, messages = extractor_with(response())
    result = extractor.extract(jpeg_document)
    kwargs = messages.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs["output_config"] == {"format": {"type": "json_schema", "schema": RECEIPT_SCHEMA}}
    assert "thinking" not in kwargs and "effort" not in json.dumps(kwargs.get("output_config"))
    assert kwargs["max_tokens"] == settings.RECEIPT_MAX_OUTPUT_TOKENS
    assert "data, not instructions" in kwargs["system"]
    block = kwargs["messages"][0]["content"][0]
    assert block["type"] == "image" and block["source"]["media_type"] == "image/jpeg"
    sent = Image.open(io.BytesIO(base64.b64decode(block["source"]["data"])))
    assert max(sent.size) <= settings.RECEIPT_IMAGE_LONG_EDGE
    assert result.raw["total"] == "31.17"
    assert result.usage["input_tokens"] == 1500 and result.usage["request_id"] == "req_test"


def test_pdf_is_sent_as_document(owner):
    document, _ = store_receipt(owner, validate_receipt(upload("r.pdf", pdf_bytes(2))), "r.pdf")
    extractor, messages = extractor_with(response())
    extractor.extract(document)
    block = messages.kwargs["messages"][0]["content"][0]
    assert block["type"] == "document" and block["source"]["media_type"] == "application/pdf"


def test_heic_uses_converted_preview(owner):
    document, _ = store_receipt(owner, validate_receipt(upload("r.heic", image_bytes("HEIF"))), "r.heic")
    extractor, messages = extractor_with(response())
    extractor.extract(document)
    assert messages.kwargs["messages"][0]["content"][0]["source"]["media_type"] == "image/jpeg"


def test_sdk_retries_disabled_and_timeout_bounded(settings):
    client = AnthropicExtractor(api_key="k", model="m").client()
    assert client.max_retries == 0
    assert client.timeout.read == settings.RECEIPT_TIMEOUT_SECONDS


@pytest.mark.parametrize("error,code,retryable", [
    (anthropic.APITimeoutError(request=REQ), "timeout", True),
    (anthropic.APIConnectionError(request=REQ), "connection", True),
    (anthropic.RateLimitError("rl", response=httpx2.Response(429, request=REQ), body=None), "rate_limited", True),
    (anthropic.InternalServerError("x", response=httpx2.Response(500, request=REQ), body=None), "provider_error", True),
    (anthropic.APIStatusError("x", response=httpx2.Response(529, request=REQ), body=None), "provider_error", True),
    (anthropic.AuthenticationError("x", response=httpx2.Response(401, request=REQ), body=None), "auth", False),
    (anthropic.BadRequestError("secret receipt text", response=httpx2.Response(400, request=REQ), body=None), "rejected", False),
    (anthropic.NotFoundError("x", response=httpx2.Response(404, request=REQ), body=None), "model", False),
])
def test_error_mapping_is_sanitised(jpeg_document, error, code, retryable):
    extractor, _ = extractor_with(error)
    with pytest.raises(ExtractionError) as exc:
        extractor.extract(jpeg_document)
    assert exc.value.code == code and exc.value.retryable is retryable
    assert "secret" not in exc.value.message


@pytest.mark.parametrize("outcome,code", [
    (response(stop_reason="refusal"), "refused"),
    (response(stop_reason="max_tokens"), "too_long"),
    (response(text="not json"), "malformed"),
    (response(text="[1, 2]"), "malformed"),
])
def test_unusable_responses_fail_permanently_with_usage(jpeg_document, outcome, code):
    extractor, _ = extractor_with(outcome)
    with pytest.raises(ExtractionError) as exc:
        extractor.extract(jpeg_document)
    assert exc.value.code == code and not exc.value.retryable
    assert exc.value.usage["input_tokens"] == 1500


def test_missing_configuration_is_honest(settings):
    settings.RECEIPT_EXTRACTOR = "anthropic"
    settings.ANTHROPIC_API_KEY = ""
    settings.RECEIPT_MODEL = "claude-haiku-4-5"
    assert get_extractor() is None
    available, message, _ = extraction_status()
    assert not available and message.startswith("Automatic extraction not configured")
    settings.ANTHROPIC_API_KEY = "k"
    settings.RECEIPT_MODEL = ""
    assert get_extractor() is None
    settings.RECEIPT_MODEL = "claude-haiku-4-5"
    assert isinstance(get_extractor(), AnthropicExtractor)
    available, _, note = extraction_status()
    assert available and "Anthropic" in note and "claude-haiku-4-5" in note
