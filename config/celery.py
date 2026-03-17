"""
Celery application for FlowRoll.

Discovered by Django via config/__init__.py.
Tasks are auto-discovered from every INSTALLED_APP's tasks.py.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("flowroll")

# Namespace "CELERY_" means all Celery config keys in settings.py
# must be prefixed with CELERY_ (e.g. CELERY_BROKER_URL).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in every installed app
app.autodiscover_tasks()
