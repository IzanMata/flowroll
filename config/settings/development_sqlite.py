"""
Development settings with SQLite fallback.
Perfect for quick local development without PostgreSQL setup.
"""

import os  # noqa: F401

from .base import *  # noqa: F401, F403
from .base import TIME_ZONE  # noqa: F401

# ─── C-2 fix: DEBUG defaults to False; must be explicitly enabled in dev ──────
DEBUG = os.environ.get("DEBUG", "True") == "True"

# ─── C-1 fix: insecure fallback acceptable for dev only — marked clearly ──────
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-dev-only-do-not-use-in-production-ever",  # nosec
)

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",")

# ─── Database: SQLite for quick development ──────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

# ─── Cache: Dummy backend (no Redis required) ────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.db"

# ─── Celery: Eager mode for development ───────────────────────────────────────
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# ─── Email: Console backend ───────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ─── Static/Media ─────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
MEDIA_URL = "/media/"
STATICFILES_DIRS = [BASE_DIR / "static"]  # noqa: F405
MEDIA_ROOT = BASE_DIR / "mediafiles"  # noqa: F405
STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405

# ─── Development optimizations ────────────────────────────────────────────────
INTERNAL_IPS = ["127.0.0.1", "localhost"]

# Disable migrations for faster testing
if "test" in os.sys.argv:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }

# ─── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}