# apps/accounts/models.py
"""
Custom User model.

Extends AbstractBaseUser + PermissionsMixin so we own the full auth
pipeline (no surprises from Django's default User fields).

Extra fields beyond Django's defaults:
  plan                — free | pro (controls daily quota)
  is_email_verified   — must be True before API calls are allowed
  email_verify_token  — UUID sent in the verification email
  email_verify_sent_at — when the verification email was last sent
"""
from __future__ import annotations

import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager,PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email: str, password: str, **extra_fields) -> "User":
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str, **extra_fields) -> "User":
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault("is_email_verified", True)
        extra_fields.setdefault("plan", "pro")
        if not extra_fields['is_staff']:
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields['is_superuser']:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):

    class Plan(models.TextChoices):
        FREE = 'free', 'Free'
        PRO = 'pro', 'Pro'

    id = models.BigAutoField(primary_key=True)
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    #Account status
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    #Plan
    plan = models.CharField(
        max_length=20,
        choices=Plan.choices,
        default=Plan.FREE,
        db_index=True,
    )

    #Email verification
    is_email_verified = models.BooleanField(default=False)
    email_verify_token = models.UUIDField(default=uuid.uuid4, editable=False)
    email_verify_sent_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'accounts_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self) -> str:
        return self.email

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def rotate_verify_token(self) -> None:
        """Generate a fresh token and record when it was sent."""
        self.email_verify_token = uuid.uuid4()
        self.email_verify_sent_at = timezone.now()
        self.save(update_fields=['email_verify_token', 'email_verify_sent_at'])