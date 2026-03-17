"""
Settings package — selects the active configuration via the DJANGO_ENV
environment variable.

  DJANGO_ENV=development  (default) → development settings
  DJANGO_ENV=production             → production settings

All tooling (manage.py, wsgi.py, asgi.py, celery.py, pytest) continues
to use DJANGO_SETTINGS_MODULE=config.settings unchanged.
"""

import os

_env = os.environ.get("DJANGO_ENV", "development")

if _env == "production":
    from .production import *  # noqa: F401, F403
else:
    from .development import *  # noqa: F401, F403
