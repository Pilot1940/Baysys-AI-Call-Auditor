import os
from pathlib import Path

from decouple import config

BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY = config("SECRET_KEY", default="dev-insecure-key-change-in-prod")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "baysys_call_audit",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="baysys"),
        "USER": config("DB_USER", default=""),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "OPTIONS": {
            "options": f"-c search_path={config('DB_SCHEMA', default='baysys_call_audit')}",
        },
    }
}

# If DATABASE_URL is set, use it (Supabase connection string)
_database_url = config("DATABASE_URL", default="")
if _database_url:
    import dj_database_url

    DATABASES["default"] = dj_database_url.parse(_database_url, conn_max_age=600)
    _db_schema = config("DB_SCHEMA", default="baysys_call_audit")
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"]["options"] = f"-c search_path={_db_schema}"

STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS — allow React dev server and CRM frontend
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3005",
]

# DRF — no global auth; set per-view
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
}

# Auth backend: "mock" for dev, "crm" for production
AUDIT_AUTH_BACKEND = config("AUDIT_AUTH_BACKEND", default="mock")
AUDIT_USE_MOCK_AUTH = AUDIT_AUTH_BACKEND == "mock"

# Speech analytics provider
SPEECH_PROVIDER_HOST = config("SPEECH_PROVIDER_HOST", default="https://api.greylabs.ai")
SPEECH_PROVIDER_API_KEY = config("SPEECH_PROVIDER_API_KEY", default="")
SPEECH_PROVIDER_API_SECRET = config("SPEECH_PROVIDER_API_SECRET", default="")
SPEECH_PROVIDER_TEMPLATE_ID = config("SPEECH_PROVIDER_TEMPLATE_ID", default="")
SPEECH_PROVIDER_CALLBACK_URL = config("SPEECH_PROVIDER_CALLBACK_URL", default="")

# Rate limiting for provider submissions
SPEECH_PROVIDER_RATE_LIMIT = config("SPEECH_PROVIDER_RATE_LIMIT", default=200, cast=int)

# Compliance rules (configurable, not hardcoded)
COMPLIANCE_CALL_WINDOW_START_HOUR = config("COMPLIANCE_CALL_WINDOW_START_HOUR", default=8, cast=int)
COMPLIANCE_CALL_WINDOW_END_HOUR = config("COMPLIANCE_CALL_WINDOW_END_HOUR", default=20, cast=int)
COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY = config("COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY", default=15, cast=int)
COMPLIANCE_FATAL_THRESHOLD = config("COMPLIANCE_FATAL_THRESHOLD", default=3, cast=int)

# Sync API endpoint — roles allowed to trigger sync
SYNC_ALLOWED_ROLES = {1, 4}  # Admin, Supervisor

# Minimum call duration (seconds) — calls shorter than this are excluded from sync
SYNC_MIN_CALL_DURATION = config("SYNC_MIN_CALL_DURATION", default=20, cast=int)

# Minutes after submission before a recording is considered stuck and eligible for polling
POLL_STUCK_AFTER_MINUTES = config("POLL_STUCK_AFTER_MINUTES", default=30, cast=int)

# Webhook IP allowlist — comma-separated; empty string means allow all
SPEECH_PROVIDER_WEBHOOK_ALLOWED_IPS = config("SPEECH_PROVIDER_WEBHOOK_ALLOWED_IPS", default="")

# URL secret — all audit endpoints are prefixed with this segment
# Use a long random string (e.g. uuid4) in production. Keep secret.
AUDIT_URL_SECRET = config("AUDIT_URL_SECRET", default="dev-secret")

# Health check token — required query param for GET /audit/<URL_SECRET>/admin/status/
AUDIT_STATUS_SECRET = config("AUDIT_STATUS_SECRET", default="dev-status-secret")
