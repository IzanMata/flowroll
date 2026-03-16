# Make Celery available as `from config import celery_app` and ensure
# it is loaded when Django starts so @shared_task decorators work correctly.
from .celery import app as celery_app

__all__ = ("celery_app",)
