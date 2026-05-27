# config/celery.py
"""
Celery application wired to Django settings.

Django's settings module is the single source of truth for all
Celery configuration — no duplication in a separate celeryconfig.py.
"""
from __future__ import annotations

import os
from celery import Celery
from celery.signals import worker_ready, worker_shutdown
import logging

logger = logging.getLogger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("grammify")

# Read all CELERY_* settings from Django settings automatically.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in every installed app's tasks.py.
app.autodiscover_tasks()


@worker_ready.connect
def on_ready(sender, **kwargs):
    logger.info("Celery worker ready.")


@worker_shutdown.connect
def on_shutdown(sender, **kwargs):
    logger.info("Celery worker shutting down.")
