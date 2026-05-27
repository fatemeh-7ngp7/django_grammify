# apps/accounts/management/commands/create_superuser_if_none.py
"""
Management command: create_superuser_if_none

Creates a superuser from environment variables if no superuser exists.
Safe to call on every container start — it's a no-op when a superuser
already exists.

Usage (in Docker entrypoint):
    python manage.py create_superuser_if_none
"""
from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Create a superuser from env vars if none exists."

    def handle(self, *args, **options) -> None:
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@grammify.io")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

        if not password:
            self.stderr.write("DJANGO_SUPERUSER_PASSWORD is not set — skipping superuser creation.")
            return

        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("Superuser already exists — skipping.")
            return

        User.objects.create_superuser(email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Superuser created: {email}"))
