"""Django settings for Room by Room.

Configuration comes from environment variables (optionally loaded from a local
``.env`` file). See ``.env.example`` for the supported names.
"""

import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or "pytest" in sys.modules or env_bool("DJANGO_ALLOW_INSECURE_KEY"):
        SECRET_KEY = "insecure-local-development-key-do-not-deploy"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set (or DJANGO_DEBUG=1 for local development).")

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
# Render sets RENDER_EXTERNAL_HOSTNAME (e.g. room-by-room.onrender.com) on web services.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.core",
    "apps.accounts",
    "apps.projects",
    "apps.shopping",
    "apps.costs",
    "apps.receipts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # static files only; private files never live there
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Every page requires login unless explicitly decorated with @login_not_required.
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


def database_from_url(url):
    parsed = urlparse(url)
    if parsed.scheme in {"postgres", "postgresql"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": unquote(parsed.hostname or ""),
            "PORT": str(parsed.port or ""),
            "CONN_MAX_AGE": 60,
            "ATOMIC_REQUESTS": False,
        }
    if parsed.scheme == "sqlite":
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": parsed.path or BASE_DIR / "db.sqlite3"}
    raise RuntimeError(f"Unsupported DATABASE_URL scheme: {parsed.scheme}")


DATABASES = {
    "default": database_from_url(os.environ["DATABASE_URL"])
    if os.environ.get("DATABASE_URL")
    else {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/Jersey"
USE_I18N = False
USE_TZ = True
USE_THOUSAND_SEPARATOR = False

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Private files (receipts, project photos). Never served by MEDIA_URL or static
# hosting: every download goes through an owner-checked view.
PRIVATE_STORAGE_ROOT = Path(os.environ.get("PRIVATE_STORAGE_ROOT", BASE_DIR / "private_storage"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # "filesystem" for local development; "database" on Render, where the web service and the
    # worker are separate machines and a persistent disk cannot be shared between them.
    "private": (
        {"BACKEND": "apps.core.storage.DatabaseStorage"}
        if os.environ.get("PRIVATE_STORAGE_BACKEND", "filesystem") == "database"
        else {"BACKEND": "apps.core.storage.PrivateFileSystemStorage", "OPTIONS": {"location": PRIVATE_STORAGE_ROOT}}
    ),
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if env_bool("STATIC_MANIFEST", False)
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

# Upload limits (see docs/receipt-processing.md).
UPLOAD_MAX_BYTES = 15 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2_621_440
RECEIPT_MAX_PDF_PAGES = 5
RECEIPT_MAX_LINES = 100
IMAGE_MAX_PIXELS = 50_000_000

# Receipt extraction. Reading is an explicit user action processed by
# `manage.py process_receipts`; without a key the UI says it is not configured.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
RECEIPT_MODEL = os.environ.get("RECEIPT_MODEL", "")  # recommended: claude-haiku-4-5 (see docs/receipt-processing.md)
RECEIPT_EXTRACTOR = os.environ.get("RECEIPT_EXTRACTOR", "anthropic")  # "fake" only for tests/labelled demos
RECEIPT_TIMEOUT_SECONDS = float(os.environ.get("RECEIPT_TIMEOUT_SECONDS", "60"))
RECEIPT_LEASE_SECONDS = int(os.environ.get("RECEIPT_LEASE_SECONDS", "180"))
RECEIPT_MAX_ATTEMPTS = 2
RECEIPT_RETRY_DELAY_SECONDS = int(os.environ.get("RECEIPT_RETRY_DELAY_SECONDS", "30"))
RECEIPT_MAX_OUTPUT_TOKENS = 8192
RECEIPT_IMAGE_LONG_EDGE = 1568  # standard-tier vision limit for claude-haiku-4-5
RECEIPT_STALE_QUEUE_SECONDS = 120
RECEIPT_FAKE_DELAY_SECONDS = float(os.environ.get("RECEIPT_FAKE_DELAY_SECONDS", "0"))  # fake extractor only  # UI hint when no worker seems to be running

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sessions: persistent sign-in on the owner's phone; explicit sign-out available.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", not DEBUG)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "SAMEORIGIN"
if env_bool("DJANGO_HTTPS", False):
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]  # Render's internal health check uses plain HTTP
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {"apps": {"level": os.environ.get("APP_LOG_LEVEL", "INFO")}},
}
