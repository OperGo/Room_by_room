"""Upload validation shared by project photos and receipts.

Files are identified by their content signature, never by filename extension.
Image decoding is bounded (pixel limit) and PDFs are checked for encryption
and page count before anything is stored.
"""

import hashlib
import io
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()
Image.MAX_IMAGE_PIXELS = settings.IMAGE_MAX_PIXELS

HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"heif"}

MIME_JPEG = "image/jpeg"
MIME_PNG = "image/png"
MIME_HEIC = "image/heic"
MIME_PDF = "application/pdf"


@dataclass
class ValidatedUpload:
    content: bytes
    mime: str
    size: int
    checksum: str
    page_count: int | None = None
    width: int | None = None
    height: int | None = None


def sniff_mime(head: bytes):
    if head.startswith(b"\xff\xd8\xff"):
        return MIME_JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return MIME_PNG
    if head.startswith(b"%PDF-"):
        return MIME_PDF
    if len(head) >= 12 and head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS:
        return MIME_HEIC
    return None


def read_bounded(uploaded_file, max_bytes=None):
    max_bytes = max_bytes or settings.UPLOAD_MAX_BYTES
    if uploaded_file.size is not None and uploaded_file.size > max_bytes:
        raise ValidationError(f"This file is larger than the {max_bytes // (1024 * 1024)} MB limit.")
    uploaded_file.seek(0)
    content = uploaded_file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValidationError(f"This file is larger than the {max_bytes // (1024 * 1024)} MB limit.")
    if not content:
        raise ValidationError("The file is empty.")
    return content


def open_image(content: bytes):
    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except Image.DecompressionBombError as exc:
        raise ValidationError("This image is too large to process safely.") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise ValidationError("This image could not be read. Try exporting it as JPEG or PNG.") from exc
    if image.width * image.height > settings.IMAGE_MAX_PIXELS:
        raise ValidationError("This image is too large to process safely.")
    return image


def validate_image(uploaded_file) -> ValidatedUpload:
    content = read_bounded(uploaded_file)
    mime = sniff_mime(content[:16])
    if mime not in {MIME_JPEG, MIME_PNG, MIME_HEIC}:
        raise ValidationError("Upload a JPEG, PNG or iPhone HEIC photo.")
    image = open_image(content)
    return ValidatedUpload(
        content=content, mime=mime, size=len(content), checksum=hashlib.sha256(content).hexdigest(),
        width=image.width, height=image.height,
    )


def validate_pdf(content: bytes):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise ValidationError("This PDF is password-protected. Remove the password and upload it again.")
        page_count = len(reader.pages)
    except ValidationError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise ValidationError("This PDF could not be read.") from exc
    if page_count < 1:
        raise ValidationError("This PDF has no pages.")
    if page_count > settings.RECEIPT_MAX_PDF_PAGES:
        raise ValidationError(f"Receipt PDFs can have at most {settings.RECEIPT_MAX_PDF_PAGES} pages.")
    return page_count


def validate_receipt(uploaded_file) -> ValidatedUpload:
    content = read_bounded(uploaded_file)
    mime = sniff_mime(content[:16])
    if mime is None:
        raise ValidationError("Upload a JPEG, PNG, HEIC photo or a PDF receipt.")
    if mime == MIME_PDF:
        pages = validate_pdf(content)
        return ValidatedUpload(content=content, mime=mime, size=len(content),
                               checksum=hashlib.sha256(content).hexdigest(), page_count=pages)
    image = open_image(content)
    return ValidatedUpload(content=content, mime=mime, size=len(content),
                           checksum=hashlib.sha256(content).hexdigest(), width=image.width, height=image.height)


def normalised_jpeg(content: bytes, max_side=2400, quality=85) -> bytes:
    """Re-encode an image as an upright JPEG without metadata (drops EXIF/GPS)."""
    image = open_image(content)
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "L"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1])
            image = background
        else:
            image = image.convert("RGB")
    image.thumbnail((max_side, max_side))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()
