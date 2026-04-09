"""
Base settings shared across all environments.
Never import this module directly — use development.py or production.py.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(os.path.join(BASE_DIR, ".env"))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third party
    "django_celery_beat",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # L-5: JWT revocation
    "corsheaders",
    "django_filters",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "drf_spectacular",
    "allauth.socialaccount.providers.google",
    # Local — core
    "core",
    "accounts",
    # Local — domain apps
    "academies",
    "athletes",
    "techniques",
    "matches",
    "attendance",
    "tatami",
    "membership",
    "community",
    "learning",
    # Local — placeholders
    "competitions",
    "stats",
    # Payments
    "payments",
    # Notifications
    "notifications",
    # Dashboard analytics
    "dashboard",
]

# L-2 fix: SecurityMiddleware MUST be first so HSTS / SSL redirect apply to
# every response including CORS preflight responses.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
SITE_ID = 1

# ─── SimpleJWT ────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,  # L-5: revoke rotated refresh tokens
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ─── Django REST Framework ────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "core.authentication.BlocklistJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # ── API versioning ────────────────────────────────────────────────────────
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.FlowRollPagination",
    "PAGE_SIZE": 20,
    "MAX_PAGE_SIZE": 100,  # SEC-6: prevent ?page_size=999999 DoS
    # L-4: Global throttling — tightened per-view for auth endpoints
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "200/hour",
        "user": "2000/hour",
        "login": "10/minute",  # custom class in config/throttles.py
        "token_refresh": "20/minute",  # custom class in config/throttles.py
        "register": "10/minute",
        "password_reset": "5/minute",
        "change_password": "10/minute",
        "email_verification": "20/minute",
        "magic_link": "5/minute",
        "phone_otp": "5/minute",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "FlowRoll API",
    "DESCRIPTION": (
        "Multi-tenant BJJ Academy Management SaaS.\n\n"
        "## Authentication\n\n"
        "All endpoints require a JWT Bearer token except `POST /api/auth/token/` "
        "and `POST /api/auth/token/refresh/`.\n\n"
        "Obtain tokens:\n"
        '```\nPOST /api/auth/token/\n{"username": "alice", "password": "secret"}\n```\n\n'
        "Attach the access token to subsequent requests:\n"
        "```\nAuthorization: Bearer <access_token>\n```\n\n"
        "Access tokens expire after **1 hour**. Refresh tokens expire after **7 days** "
        "and are blacklisted on rotation.\n\n"
        "## Multi-tenancy\n\n"
        "All tenant-scoped endpoints require `?academy=<id>` (or `?academy_id=<id>` "
        "for the athletes endpoint). The requesting user must have an active "
        "`AcademyMembership` for the specified academy; without it the queryset "
        "silently returns empty (tenant isolation, not a 403)."
    ),
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # JWT Bearer security scheme
    "SECURITY": [{"jwtAuth": []}],
    "SECURITY_DEFINITIONS": {
        "jwtAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "JWT access token. Obtain via POST /api/auth/token/. "
                "Include as: Authorization: Bearer <token>"
            ),
        }
    },
    # Enum name generation
    "ENUM_GENERATE_CHOICE_DESCRIPTION": True,
    # Tags for grouping in Swagger UI
    "TAGS": [
        {"name": "auth", "description": "JWT token obtain and refresh"},
        {"name": "academies", "description": "Academy (tenant) management"},
        {"name": "athletes", "description": "Athlete profile management"},
        {"name": "techniques", "description": "Platform-wide BJJ technique library"},
        {
            "name": "attendance",
            "description": "Training classes, QR check-in, drop-in visitors",
        },
        {"name": "matches", "description": "Live match scoring (professor only)"},
        {"name": "tatami", "description": "Live session tools: timers and matchmaking"},
        {
            "name": "membership",
            "description": "Plans, subscriptions, promotions, seminars",
        },
        {"name": "community", "description": "Achievements and open mat sessions"},
        {
            "name": "learning",
            "description": "Technique journals, video library, sparring notes",
        },
    ],
}

# ─── Password validation ──────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─── Internationalisation ─────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ─── Static & media files ─────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── Google OAuth ─────────────────────────────────────────────────────────────
# Set GOOGLE_CLIENT_ID in your .env file (obtain from Google Cloud Console).
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# ─── Apple Sign-In ────────────────────────────────────────────────────────────
# Service ID (web) or Bundle ID (native app) registered in Apple Developer Portal.
APPLE_CLIENT_ID = os.environ.get("APPLE_CLIENT_ID", "")

# ─── Twilio (Phone OTP) ───────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")

# ─── Stripe Connect Express ───────────────────────────────────────────────────
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
# Pin the API version to avoid breaking changes on Stripe SDK upgrades.
STRIPE_API_VERSION = "2024-06-20"
# Marketplace commission: % of each payment kept by the platform.
# e.g. 10.0 means FlowRoll keeps 10 % and the academy receives 90 % (minus Stripe fees).
STRIPE_PLATFORM_FEE_PERCENT = float(os.environ.get("STRIPE_PLATFORM_FEE_PERCENT", "10.0"))
