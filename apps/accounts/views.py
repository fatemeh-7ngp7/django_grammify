# apps/accounts/views.py
"""
Auth API views.

Endpoints:
  POST /api/auth/register              — create account, send verification email
  POST /api/auth/login                 — obtain JWT pair (requires verified email)
  POST /api/auth/token/refresh         — rotate refresh token
  POST /api/auth/logout                — blacklist refresh token
  GET  /api/auth/verify-email          — confirm email with ?token=<uuid>
  POST /api/auth/resend-verification   — resend verification email
  GET  /api/auth/me                    — profile + quota
  PATCH /api/auth/me                   — update name
  POST /api/auth/change-password       — change password
"""
from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from utils.metrics import auth_registrations, auth_logins
from .emails import send_verification_email
from .serializers import (
    ChangePasswordSerializer,
    RegisterSerializer,
    UpdateProfileSerializer,
    UserProfileSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterView(APIView):
    """Register a new user and send the verification email."""
    
    permission_classes = [AllowAny]
    throttle_scope = "anon"

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Send verification email (non-blocking — failure is logged, not raised)
        user.rotate_verify_token()
        send_verification_email(user)

        auth_registrations.inc()
        logger.info("New user registered: %s", user.email)

        return Response(
            {
                "message": (
                    "Account created. Please check your email to verify your address "
                    "before logging in."
                ),
                "email": user.email,
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Login (JWT token pair)
# ---------------------------------------------------------------------------

class LoginView(TokenObtainPairView):
    """
    Obtain access + refresh JWT tokens.
    Returns the user profile alongside the tokens.
    Requires email to be verified.
    """
    permission_classes = [AllowAny]

    def post(self, request: Request, *args, **kwargs) -> Response:
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            auth_logins.inc()
            logger.info("User logged in: %s", request.data.get("email"))
        return response


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class LogoutView(APIView):
    """
    Blacklist the supplied refresh token (invalidates that session).
    The frontend should also delete the access token and user info.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info("User logged out: %s", request.user.email)
        except Exception as exc:
            logger.warning("Logout failed for user %s: %s", request.user.email, exc)
            return Response(
                {"error": "Invalid or already-expired refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
            
        return Response(
            {"message": "Logged out successfully."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

class VerifyEmailView(APIView):
    """
    Verify the user's email address using the token from the verification link.
    GET /api/auth/verify-email?token=<uuid> — mark email as verified.
    """
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        token = request.query_params.get("token", "").strip()
        if not token:
            return Response(
                {"error": "Verification token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email_verify_token=token)
        except User.DoesNotExist:
            return Response(
                {"error": "Invalid or expired verification token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.is_email_verified:
            return Response({"message": "Email is already verified."})

        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
        logger.info("Email verified for user: %s", user.email)

        return Response(
            {"message": "Email verified successfully. You can now log in."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Resend verification
# ---------------------------------------------------------------------------

class ResendVerificationView(APIView):
    """POST /api/auth/resend-verification — resend the email verification link."""
    permission_classes = [AllowAny]
    throttle_scope = "anon"

    def post(self, request: Request) -> Response:
        email = request.data.get("email", "").strip().lower()
        if not email:
            return Response(
                {"error": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email, is_email_verified=False)
            user.rotate_verify_token()
            send_verification_email(user)
            logger.info("Resent verification email to: %s", user.email)
        except User.DoesNotExist:
            # Don't reveal whether the email exists — just respond with success.
            logger.warning("Resend verification requested for non-existent email: %s", email)
            pass
        
        return Response(
                {"message": "If that email is registered and unverified, a verification link has been sent."}
            )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class MeView(APIView):
    """GET /api/auth/me — return profile info for the logged-in user."""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = UserProfileSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    def patch(self, request: Request) -> Response:
        """Allow updating first_name and last_name."""
        serializer = UpdateProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        logger.info("User updated profile: %s", request.user.email)
        return Response(UserProfileSerializer(request.user, context={"request": request}).data)


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

class ChangePasswordView(APIView):
    """
    Allow logged-in users to change their password.
    POST /api/auth/change-password — change password for authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        logger.info("Password changed for user: %s", request.user.email)
        return Response({"message": "Password changed successfully."})