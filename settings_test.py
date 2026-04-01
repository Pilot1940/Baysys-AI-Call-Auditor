"""
Test settings — overrides DATABASE to SQLite in-memory.
Use:
  python manage.py test --settings=settings_test -v 0
"""
import os

os.environ.setdefault("AUDIT_AUTH_BACKEND", "mock")

from settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
