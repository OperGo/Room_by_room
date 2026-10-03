"""Receipt extraction boundary.

``ReceiptExtractor.extract(document) -> ReceiptExtractionResult`` is the only
interface the rest of the app depends on. Sprint 1 ships no live adapter: the
UI reports that automatic extraction is not available and the owner reviews
the receipt manually. The Anthropic adapter, job worker and fake test adapter
arrive in Sprint 2 (see docs/receipt-processing.md).
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings


@dataclass
class ExtractedLine:
    description: str
    line_total: Decimal | None
    quantity: Decimal | None = None
    kind: str = "item"  # item / shipping / discount / tax / rounding


@dataclass
class ReceiptExtractionResult:
    merchant: str | None = None
    receipt_date: str | None = None
    currency: str | None = None
    total: Decimal | None = None
    receipt_number: str | None = None
    lines: list[ExtractedLine] = field(default_factory=list)
    uncertain_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model_version: str = ""
    usage: dict = field(default_factory=dict)


class ExtractionUnavailable(Exception):
    pass


class ReceiptExtractor:
    name = "base"

    def extract(self, document) -> ReceiptExtractionResult:  # pragma: no cover - interface
        raise NotImplementedError


class NotConfiguredExtractor(ReceiptExtractor):
    name = "not-configured"

    def extract(self, document):
        raise ExtractionUnavailable("Automatic extraction is not configured.")


def extraction_status():
    """Return (available, message) for the UI."""
    if not settings.RECEIPT_EXTRACTION_ENABLED:
        return False, "Automatic receipt reading is not available yet. Enter the details from the receipt."
    if not settings.ANTHROPIC_API_KEY or not settings.RECEIPT_MODEL:
        return False, "Automatic extraction not configured. Enter the details from the receipt."
    return True, ""


def get_extractor() -> ReceiptExtractor:
    return NotConfiguredExtractor()
