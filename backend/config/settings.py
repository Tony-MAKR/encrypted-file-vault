"""Django settings for the encrypted file vault.

The project currently contains the foundation and the account/role layer:
configuration, logging, database connectivity, sessions, authentication and a
small security baseline. File storage and content authorization are added in
later stages.
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from apps.core.staticfiles import add_static_headers
from config.security import validate_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")

APP_VERSION = "0.6.0"


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


SECRET_KEY = validate_secret_key(os.getenv("DJANGO_SECRET_KEY"))
DEBUG = _get_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = _get_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "出于安全考虑，DJANGO_ALLOWED_HOSTS 不允许使用通配符 *。"
    )

# ---------------------------------------------------------------------------
# Data directories
# ---------------------------------------------------------------------------
# Everything the application owns lives under DATA_DIR. In particular, the
# SQLite database and future encrypted vault files must never be placed in a
# directory that is served statically by a web server.
DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser()
if not DATA_DIR.is_absolute():
    DATA_DIR = (PROJECT_ROOT / DATA_DIR).resolve()

DB_DIR = DATA_DIR / "db"
LOG_DIR = DATA_DIR / "logs"
VAULT_DIR = DATA_DIR / "vault"
VAULT_OBJECTS_DIR = VAULT_DIR / "objects"
VAULT_TMP_DIR = VAULT_DIR / "tmp"
KEYS_DIR = DATA_DIR / "keys"
BACKUP_DIR = DATA_DIR / "backups"

for _directory in (
    DB_DIR,
    LOG_DIR,
    VAULT_DIR,
    VAULT_OBJECTS_DIR,
    VAULT_TMP_DIR,
    KEYS_DIR,
    BACKUP_DIR,
):
    _directory.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.vault",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves the built React application (and nothing under DATA_DIR) directly
    # from FRONTEND_DIST_DIR. It runs before Django URL routing so hashed
    # assets are returned with long-lived cache headers.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # SecurityHeaders is outer to the custom account middleware so direct
    # 401/403 responses also receive no-store and hardening headers.
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.accounts.middleware.SessionTimeoutMiddleware",
    "apps.accounts.middleware.MustChangePasswordMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DB_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 20,
        },
    }
}

# ---------------------------------------------------------------------------
# Authentication and API defaults
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {
            "user_attributes": ("username", "display_name", "email"),
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    # API only: do not expose Django's browsable HTML interface.
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # Failing closed means any future endpoint that forgets an explicit
    # permission will be inaccessible rather than public.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.SessionAuthentication401",
    ],
}

# Used by DRF's IP-based login/setup throttles. A later production stage can
# replace this with Redis; for a single-host local deployment this is enough.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "encrypted-file-dev-cache",
    }
}

# ---------------------------------------------------------------------------
# CORS / CSRF (development origin only)
# ---------------------------------------------------------------------------
FRONTEND_DEV_ORIGIN = os.getenv(
    "FRONTEND_DEV_ORIGIN", "http://127.0.0.1:5173"
).rstrip("/")
CORS_ALLOWED_ORIGINS = _get_list(
    "CORS_ALLOWED_ORIGINS",
    f"{FRONTEND_DEV_ORIGIN},http://localhost:5173",
)
CORS_ALLOWED_ORIGINS = list(dict.fromkeys(CORS_ALLOWED_ORIGINS))
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ["Content-Disposition"]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# ---------------------------------------------------------------------------
# Security baseline
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = False
CSRF_COOKIE_SAMESITE = "Lax"
# The SPA must read the CSRF cookie to copy it into the X-CSRFToken header.
CSRF_COOKIE_HTTPONLY = False
CSRF_FAILURE_VIEW = "apps.accounts.views_auth.csrf_failure"
SESSION_COOKIE_SECURE = _get_bool("DJANGO_SECURE_COOKIES", False)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT = _get_bool("DJANGO_SECURE_SSL_REDIRECT", False)

# Session lifetime and login lockout (balanced security profile).
SESSION_IDLE_TIMEOUT_SECONDS = _get_int("SESSION_IDLE_TIMEOUT_SECONDS", 30 * 60)
SESSION_ABSOLUTE_TIMEOUT_SECONDS = _get_int(
    "SESSION_ABSOLUTE_TIMEOUT_SECONDS", 8 * 60 * 60
)
LOGIN_MAX_FAILED_ATTEMPTS = _get_int("LOGIN_MAX_FAILED_ATTEMPTS", 5)
LOGIN_LOCKOUT_MINUTES = _get_int("LOGIN_LOCKOUT_MINUTES", 15)

# HSTS is enabled only after HTTPS is configured in a later stage.
SECURE_HSTS_SECONDS = 0

# ---------------------------------------------------------------------------
# Vault encryption
# ---------------------------------------------------------------------------
# The master key file contains only a wrapped master key. The master password
# is never stored. Tests override these paths with a temporary directory.
VAULT_KEY_FILE = KEYS_DIR / "master.key.json"
VAULT_MAX_FILE_SIZE_MB = _get_int("VAULT_MAX_FILE_SIZE_MB", 200)
VAULT_MAX_FILE_SIZE_BYTES = VAULT_MAX_FILE_SIZE_MB * 1024 * 1024
VAULT_TRASH_RETENTION_DAYS = _get_int("VAULT_TRASH_RETENTION_DAYS", 30)
VAULT_CHUNK_SIZE = 1024 * 1024
VAULT_KDF_TIME_COST = _get_int("VAULT_KDF_TIME_COST", 3)
VAULT_KDF_MEMORY_COST = _get_int("VAULT_KDF_MEMORY_COST", 65536)
VAULT_KDF_PARALLELISM = _get_int("VAULT_KDF_PARALLELISM", 4)

# ---------------------------------------------------------------------------
# Internationalization and static files
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = DATA_DIR / "staticfiles"
STATIC_ROOT.mkdir(parents=True, exist_ok=True)

# Production / desktop webpage assets. The frontend build writes to this
# directory; WhiteNoise serves it, and a small Django fallback returns
# index.html for React routes. The directory is separate from DATA_DIR so
# databases, keys and ciphertext can never be exposed through it.
FRONTEND_DIST_DIR = Path(
    os.getenv("FRONTEND_DIST_DIR", str(PROJECT_ROOT / "frontend" / "dist"))
).expanduser()
if not FRONTEND_DIST_DIR.is_absolute():
    FRONTEND_DIST_DIR = (PROJECT_ROOT / FRONTEND_DIST_DIR).resolve()

WHITENOISE_ROOT = str(FRONTEND_DIST_DIR) if FRONTEND_DIST_DIR.is_dir() else None
WHITENOISE_ALLOW_ALL_ORIGINS = False
WHITENOISE_ADD_HEADERS_FUNCTION = add_static_headers

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
if LOG_LEVEL not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
    LOG_LEVEL = "INFO"

LOG_FILE = LOG_DIR / "app.log"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.core.logging.RequestIDFilter"},
        "redact": {"()": "apps.core.logging.RedactSensitiveFilter"},
    },
    "formatters": {
        "json": {"()": "apps.core.logging.JsonFormatter"},
        "console": {"()": "apps.core.logging.SafeConsoleFormatter"},
    },
    "handlers": {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_FILE),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "json",
            "filters": ["request_id", "redact"],
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
            "filters": ["request_id", "redact"],
        },
    },
    "root": {
        "handlers": ["file", "console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["file", "console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "django.server": {
            "handlers": ["file", "console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["file", "console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}
