# apps/accounts/serializers.py
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from utils.quota import get_usage

User = get_user_model()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterSerializer(serializers.ModelSerializer):
    """Validate and create a new user account."""

    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})
    password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'password', 'password_confirm']
        extra_kwargs = {
            "first_name": {"required": False},
            "last_name": {"required": False},
        }

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data: dict) -> User:
        return User.objects.create_user(**validated_data)


# ---------------------------------------------------------------------------
# JWT token pair with extra claims
# ---------------------------------------------------------------------------

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extend the default JWT payload with user-specific claims so the
    frontend has everything it needs without an extra /me call.
    """

    def validate(self, attrs: dict) -> dict:
        data = super().validate(attrs)
        user: User = self.user  # type: ignore[override]
        
        if not user.is_email_verified:
            raise serializers.ValidationError(
                "Please verify your email address before logging in. "
                "Check your inbox for a verification link."
            )

        data["user"] = UserProfileSerializer(user).data
        return data

    @classmethod
    def get_token(cls, user: User):  # type: ignore[override]
        token = super().get_token(user)
        token["email"] = user.email
        token["plan"] = user.plan
        token["is_email_verified"] = user.is_email_verified
        return token


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class UserProfileSerializer(serializers.ModelSerializer):
    """Read-only user profile — safe to expose to the client."""

    full_name = serializers.CharField(read_only=True)
    quota = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'first_name',
            'last_name',
            'full_name',
            'plan',
            'is_email_verified',
            'date_joined',
            'quota',
        ]
        read_only_fields = fields

    def get_quota(self, user: User) -> dict:
        request = self.context.get("request")
        ip = request.META.get("REMOTE_ADDR", "0.0.0.0") if request else "0.0.0.0"
        result = get_usage(user_id=user.pk, user_plan=user.plan, ip=ip)
        return {
            "limit": result.limit,
            "used": result.used,
            "remaining": result.remaining,
            "resets_in_seconds": result.resets_in_seconds,
        }


# ---------------------------------------------------------------------------
# Profile update (PATCH /me)
# ---------------------------------------------------------------------------

class UpdateProfileSerializer(serializers.ModelSerializer):
    """Allow users to update their profile info (except email)."""
    class Meta:
        model = User
        fields = ['first_name', 'last_name']


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

class ChangePasswordSerializer(serializers.Serializer):
    """Allow users to change their password by providing the old one."""
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_old_password(self, value: str) -> str:
        user: User = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value: str) -> str:
        try:
            validate_password(value, self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
        return attrs

    def save(self, **kwargs) -> None:
        user: User = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])