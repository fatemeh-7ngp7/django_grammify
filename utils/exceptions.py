# utils/exceptions.py
"""
Custom DRF exception handler.

Ensures every unhandled exception — including Django's Http404 and
PermissionDenied — is returned as our standard JSON envelope,
even for endpoints that DRF would otherwise render as HTML.
"""
from __future__ import annotations

import logging

from django.http import Http404
from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def grammify_exception_handler(exc, context):
    """
    Extend DRF's default handler to cover Django exceptions and
    add server-side logging for unexpected 5xx errors.
    """
    # Map Django exceptions to DRF equivalents so the default handler
    # can render them correctly.
    if isinstance(exc, Http404):
        from rest_framework.exceptions import NotFound
        exc = NotFound()
    elif isinstance(exc, PermissionDenied):
        from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
        exc = DRFPermissionDenied()
    elif isinstance(exc, ValidationError):
        from rest_framework.exceptions import ValidationError as DRFValidationError
        exc = DRFValidationError(detail=exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

    response = drf_exception_handler(exc, context)

    if response is None:
        # Completely unhandled exception — log it and return 500.
        logger.exception("Unhandled exception in %s", context.get("view"))
        return Response(
            {"success": False, "error": "An unexpected error occurred."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if response.status_code >= 500:
        logger.error("Server error %s: %s", response.status_code, exc)

    return response
