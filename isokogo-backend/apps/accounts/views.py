import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserVerification

User = get_user_model()

VERIFICATION_CODE_TTL_MINUTES = 10
MAX_CODES_PER_HOUR = 5
VERIFICATION_TYPES = {"email", "phone"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def serialize_user(user):
    return {
        "id": user.id,
        "email": user.email,
        "phone_number": user.phone_number,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "date_joined": user.date_joined,
        "updated_at": user.updated_at,
    }


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


def generate_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def send_verification_code(user, verification_type, code):
    """
    Plug in your email / SMS provider here (SMTP, Twilio, Africa's Talking, ...).
    The print below is for development only. Never log codes in production.
    """
    print(f"[DEV] {verification_type} code for {user.email}: {code}")


def create_verification(user, verification_type):
    code = generate_code()
    UserVerification.objects.create(
        user=user,
        verification_type=verification_type,
        verification_code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=VERIFICATION_CODE_TTL_MINUTES),
    )
    send_verification_code(user, verification_type, code)


def error(message, http_status=status.HTTP_400_BAD_REQUEST, **extra):
    return Response({"error": message, **extra}, status=http_status)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------
class IsAdminRole(BasePermission):
    """Allows access only to authenticated users whose role is 'admin'."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == "admin")


# ---------------------------------------------------------------------------
# Auth views
# ---------------------------------------------------------------------------
class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data
        required = ["email", "phone_number", "first_name", "last_name", "password"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            return error("Missing required fields.", fields=missing)

        email = data["email"].strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            return error("Invalid email address.")

        phone_number = data["phone_number"].strip()
        candidate = User(
            email=email,
            phone_number=phone_number,
            first_name=data["first_name"].strip(),
            last_name=data["last_name"].strip(),
        )
        try:
            validate_password(data["password"], user=candidate)
        except ValidationError as exc:
            return error("Password is too weak.", errors=list(exc.messages))

        if User.objects.filter(email=email).exists():
            return error("Email already registered.", status.HTTP_409_CONFLICT)
        if User.objects.filter(phone_number=phone_number).exists():
            return error("Phone number already registered.", status.HTTP_409_CONFLICT)

        try:
            with transaction.atomic():
                # `role` is deliberately not read from the request body.
                user = User.objects.create_user(
                    email=email,
                    password=data["password"],
                    phone_number=phone_number,
                    first_name=candidate.first_name,
                    last_name=candidate.last_name,
                )
                create_verification(user, "email")
        except IntegrityError:
            return error("User already exists.", status.HTTP_409_CONFLICT)

        return Response(
            {
                "message": "Registered. A verification code has been sent.",
                "user": serialize_user(user),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        password = request.data.get("password") or ""

        user = User.objects.filter(email=email).first()
        # One generic message for unknown email and wrong password
        # so the endpoint can't be used to discover registered emails.
        if user is None or not user.check_password(password):
            return error("Invalid credentials.", status.HTTP_401_UNAUTHORIZED)
        if not user.is_active:
            return error("Account is disabled.", status.HTTP_403_FORBIDDEN)

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        return Response({"tokens": get_tokens_for_user(user), "user": serialize_user(user)})


class LogoutView(APIView):
    """
    Blacklists the refresh token. Requires 'rest_framework_simplejwt.token_blacklist'
    in INSTALLED_APPS (and `python manage.py migrate`).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return error("refresh token is required.")
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return error("Invalid or expired token.")
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Verification views
# ---------------------------------------------------------------------------
class SendVerificationCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        verification_type = request.data.get("verification_type", "email")
        if verification_type not in VERIFICATION_TYPES:
            return error("verification_type must be 'email' or 'phone'.")
        if request.user.is_verified:
            return Response({"message": "Account is already verified."})

        recent = UserVerification.objects.filter(
            user=request.user,
            created_at__gte=timezone.now() - timedelta(hours=1),
        ).count()
        if recent >= MAX_CODES_PER_HOUR:
            return error("Too many requests. Try again later.", status.HTTP_429_TOO_MANY_REQUESTS)

        create_verification(request.user, verification_type)
        return Response({"message": "Verification code sent."})


class VerifyCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        verification_type = request.data.get("verification_type", "email")
        code = str(request.data.get("code", "")).strip()
        if verification_type not in VERIFICATION_TYPES:
            return error("verification_type must be 'email' or 'phone'.")
        if not code:
            return error("code is required.")

        verification = (
            UserVerification.objects.filter(
                user=request.user,
                verification_type=verification_type,
                is_verified=False,
                expires_at__gt=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )
        if verification is None or not check_password(code, verification.verification_code_hash):
            return error("Invalid or expired code.")

        with transaction.atomic():
            verification.is_verified = True
            verification.save(update_fields=["is_verified"])
            request.user.is_verified = True
            request.user.save(update_fields=["is_verified", "updated_at"])

        return Response({"message": "Verified successfully.", "user": serialize_user(request.user)})


# ---------------------------------------------------------------------------
# Current-user views
# ---------------------------------------------------------------------------
class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    editable_fields = ("first_name", "last_name", "phone_number")

    def get(self, request):
        return Response(serialize_user(request.user))

    def patch(self, request):
        user = request.user
        changed = []

        for field in self.editable_fields:
            value = request.data.get(field)
            if value is None:
                continue
            value = str(value).strip()
            if not value:
                return error(f"{field} cannot be empty.")
            if (
                field == "phone_number"
                and User.objects.filter(phone_number=value).exclude(pk=user.pk).exists()
            ):
                return error("Phone number already in use.", status.HTTP_409_CONFLICT)
            setattr(user, field, value)
            changed.append(field)

        if changed:
            user.save(update_fields=changed + ["updated_at"])
        return Response(serialize_user(user))


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_password = request.data.get("old_password") or ""
        new_password = request.data.get("new_password") or ""

        if not request.user.check_password(old_password):
            return error("Old password is incorrect.")
        try:
            validate_password(new_password, user=request.user)
        except ValidationError as exc:
            return error("New password is too weak.", errors=list(exc.messages))

        request.user.set_password(new_password)
        request.user.save(update_fields=["password", "updated_at"])
        return Response({"message": "Password changed. Please log in again on other devices."})


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------
class UserListView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        qs = User.objects.all().order_by("-date_joined")

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone_number__icontains=search)
            )

        role = request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)

        is_active = request.query_params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))

        try:
            page = max(int(request.query_params.get("page", 1)), 1)
            page_size = min(max(int(request.query_params.get("page_size", 20)), 1), 100)
        except ValueError:
            return error("Invalid pagination values.")

        total = qs.count()
        start = (page - 1) * page_size
        results = [serialize_user(u) for u in qs[start : start + page_size]]
        return Response({"count": total, "page": page, "page_size": page_size, "results": results})


class UserDetailView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request, pk):
        return Response(serialize_user(get_object_or_404(User, pk=pk)))

    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        is_self = user.pk == request.user.pk
        changed = []

        role = request.data.get("role")
        if role is not None:
            if role not in dict(User.ROLE_CHOICES):
                return error("Invalid role.")
            if is_self and role != user.role:
                return error("You cannot change your own role.")
            user.role = role
            changed.append("role")

        for flag in ("is_active", "is_verified"):
            if flag in request.data:
                value = bool(request.data[flag])
                if is_self and flag == "is_active" and not value:
                    return error("You cannot deactivate your own account.")
                setattr(user, flag, value)
                changed.append(flag)

        if changed:
            user.save(update_fields=changed + ["updated_at"])
        return Response(serialize_user(user))

    def delete(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user.pk == request.user.pk:
            return error("You cannot delete your own account.")
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)