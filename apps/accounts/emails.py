# apps/accounts/emails.py
"""
Email sending helpers for the accounts app.

All templates are inline strings so no template files are required.
In production, swap EMAIL_BACKEND to an SMTP or transactional provider.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_verification_email(user) -> None:
    """Send the email verification link to a newly registered user."""
    verify_url =(
        f"{settings.FRONTEND_URL}/verify-email?token={user.email_verify_token}"
    )

    subject = 'Verify your Grammify email address'
    text_body = (
        f"Hi {user.first_name or 'there'},\n\n"
        f"Thanks for registering with Grammify!\n\n"
        f"Click the link below to verify your email address:\n"
        f"{verify_url}\n\n"
        f"If you didn't create an account, you can safely ignore this email.\n\n"
        f"— The Grammify Team"
    )

    try:
        send_mail(
            subject=subject,
            message=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info("Verification email sent to %s", user.email)
    except Exception as exc:
        # Log but don't raise — the user was created successfully; the email
        # can be resent via /auth/resend-verification.
        logger.error("Failed to send verification email to %s: %s", user.email, exc)


def send_password_reset_email(user, token: str) -> None:
    """Send a password reset link (stub — implement when needed)."""
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    subject = 'Reset your Grammify password'
    text_body = (
        f"Hi {user.first_name or 'there'},\n\n"
        f"We received a request to reset your Grammify password.\n\n"
        f"Click the link below to set a new password:\n"
        f"{reset_url}\n\n"
        f"This link expires in 1 hour.\n\n"
        f"If you didn't request this, you can safely ignore this email.\n\n"
        f"— The Grammify Team"
    )
    try:
        send_mail(
            subject=subject,
            message=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info("Password reset email sent to %s", user.email)
    except Exception as exc:
        logger.error("Failed to send password reset email to %s: %s", user.email, exc)