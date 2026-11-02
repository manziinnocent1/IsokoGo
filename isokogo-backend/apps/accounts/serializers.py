from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from .models import UserVerification

User = get_user_model()

VERIFICATION_TYPE_CHOICES = [choice[0] for choice in UserVerification.VERIFICATION_TYPES]


def run_password_validators(password, user=None):
    """Run Django's AUTH_PASSWORD_VALIDATORS and convert errors to DRF errors."""
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages))
    return password


# ---------------------------------------------------------------------------
# Output serializers
# ---------------------------------------------------------------------------
class UserSerializer(serializers.ModelSerializer):
    """Read-only representation of a user. Never exposes the password."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone_number",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "is_active",
            "is_verified",
            "date_joined",
            "updated_at",
        ]
        read_only_fields = fields


class UserVerificationSerializer(serializers.ModelSerializer):
    """Read-only view of a verification record. The code hash is never exposed."""

    class Meta:
        model = UserVerification
        fields = ["id", "user", "verification_type", "expires_at", "is_verified", "created_at"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Auth serializers
# ---------------------------------------------------------------------------
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["email", "phone_number", "first_name", "last_name", "password"]
        # Uniqueness is checked manually below so email matching is case-insensitive.
        extra_kwargs = {
            "email": {"validators": []},
            "phone_number": {"validators": []},
        }

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate_phone_number(self, value):
        value = value.strip()
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("Phone number already registered.")
        return value

    def validate(self, attrs):
        # Validate the password against the other submitted fields
        # (rejects passwords too similar to the email or name).
        candidate = User(**{k: v for k, v in attrs.items() if k != "password"})
        try:
            run_password_validators(attrs["password"], user=candidate)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"password": exc.detail})
        return attrs

    def create(self, validated_data):
        # `role` is not an input field, so nobody can self-register as admin.
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        user = User.objects.filter(email__iexact=email).first()

        # Same message for unknown email and wrong password,
        # so the endpoint can't be used to discover registered emails.
        if user is None or not user.check_password(attrs["password"]):
            raise AuthenticationFailed("Invalid credentials.")
        if not user.is_active:
            raise PermissionDenied("Account is disabled.")

        attrs["user"] = user
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


# ---------------------------------------------------------------------------
# Verification serializers
# ---------------------------------------------------------------------------
class SendVerificationCodeSerializer(serializers.Serializer):
    verification_type = serializers.ChoiceField(choices=VERIFICATION_TYPE_CHOICES, default="email")


class VerifyCodeSerializer(serializers.Serializer):
    verification_type = serializers.ChoiceField(choices=VERIFICATION_TYPE_CHOICES, default="email")
    code = serializers.RegexField(
        r"^\d{6}$",
        error_messages={"invalid": "Code must be exactly 6 digits."},
    )


# ---------------------------------------------------------------------------
# Current-user serializers
# ---------------------------------------------------------------------------
class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Fields a user may edit on their own profile (use with partial=True)."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone_number"]
        # The model's unique validator already excludes the current instance on update.


class ChangePasswordSerializer(serializers.Serializer):
    """Expects `context={"request": request}`."""

    old_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate_new_password(self, value):
        return run_password_validators(value, user=self.context["request"].user)

    def validate(self, attrs):
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {"new_password": "New password must be different from the old password."}
            )
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


# ---------------------------------------------------------------------------
# Admin serializers
# ---------------------------------------------------------------------------
class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """
    Lets an admin change role / active / verified flags (use with partial=True).
    Expects `context={"request": request}`.
    """

    class Meta:
        model = User
        fields = ["role", "is_active", "is_verified"]

    def validate(self, attrs):
        request = self.context.get("request")
        is_self = request is not None and self.instance is not None and self.instance.pk == request.user.pk

        if is_self:
            if "role" in attrs and attrs["role"] != self.instance.role:
                raise serializers.ValidationError({"role": "You cannot change your own role."})
            if attrs.get("is_active") is False:
                raise serializers.ValidationError({"is_active": "You cannot deactivate your own account."})
        return attrs


class UserListQuerySerializer(serializers.Serializer):
    """Validates query-string filters and pagination for the admin user list."""

    search = serializers.CharField(required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=[c[0] for c in User.ROLE_CHOICES], required=False)
    is_active = serializers.BooleanField(required=False)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)