"""
Pytest tests for the accounts app (models, serializers, views).

Requirements:
    pip install pytest pytest-django

The views are called directly with APIRequestFactory, so these tests do not
depend on your urls.py. Every test that touches the database gets it through
the `db` fixture (or the `pytest.mark.django_db` mark).

Assumptions about settings:
  * AUTH_PASSWORD_VALIDATORS is configured (Django's defaults are fine).
  * 'rest_framework_simplejwt.token_blacklist' is in INSTALLED_APPS
    (needed for the logout tests).
"""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from . import views
from .models import User, UserVerification
from .serializers import (
    AdminUserUpdateSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserListQuerySerializer,
    UserSerializer,
    UserVerificationSerializer,
    VerifyCodeSerializer,
)

pytestmark = pytest.mark.django_db

STRONG_PASSWORD = "Tr0ub4dor&Zebra-Lamp-92"
OTHER_STRONG_PASSWORD = "Gr33n-Mango!Sunrise_17"
WEAK_PASSWORD = "12345678"


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def make_user():
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        n = counter["n"]
        params = {
            "email": f"user{n}@example.com",
            "password": STRONG_PASSWORD,
            "phone_number": f"0788{n:06d}",
            "first_name": "Test",
            "last_name": f"User{n}",
        }
        params.update(overrides)
        return User.objects.create_user(**params)

    return _make


@pytest.fixture
def user(make_user):
    return make_user(email="alice@example.com")


@pytest.fixture
def admin(make_user):
    return make_user(email="admin@example.com", role="admin")


@pytest.fixture
def sent_codes(monkeypatch):
    """Capture verification codes instead of 'sending' them."""
    sent = []
    monkeypatch.setattr(
        views,
        "send_verification_code",
        lambda user, verification_type, code: sent.append((user, verification_type, code)),
    )
    return sent


@pytest.fixture
def call(factory):
    """call(ViewClass, "post", data={...}, user=u, query={...}, **url_kwargs)"""

    def _call(view_class, method, data=None, user=None, query=None, **url_kwargs):
        make = getattr(factory, method)
        path = "/test/"
        if method == "get":
            request = make(path, query or {})
        elif method == "delete":
            request = make(path)
        else:
            request = make(path, data or {}, format="json")
        if user is not None:
            force_authenticate(request, user=user)
        return view_class.as_view()(request, **url_kwargs)

    return _call


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------
class TestUserModel:
    def test_create_user_defaults(self, make_user):
        u = make_user()
        assert u.role == "user"
        assert u.is_active is True
        assert u.is_verified is False
        assert u.is_superuser is False
        assert u.is_staff is False
        assert u.is_admin is False
        assert u.check_password(STRONG_PASSWORD)

    def test_email_is_lowercased(self, make_user):
        u = make_user(email="MixedCase@Example.COM")
        assert u.email == "mixedcase@example.com"

    def test_create_user_requires_email(self):
        with pytest.raises(ValueError):
            User.objects.create_user(email="", password=STRONG_PASSWORD)

    def test_create_superuser(self):
        su = User.objects.create_superuser(
            email="root@example.com",
            password=STRONG_PASSWORD,
            phone_number="0700000001",
            first_name="Root",
            last_name="User",
        )
        assert su.role == "admin"
        assert su.is_superuser is True
        assert su.is_verified is True
        assert su.is_staff is True
        assert su.is_admin is True

    def test_create_superuser_rejects_non_admin_role(self):
        with pytest.raises(ValueError):
            User.objects.create_superuser(
                email="bad@example.com",
                password=STRONG_PASSWORD,
                role="user",
                phone_number="0700000002",
                first_name="Bad",
                last_name="Root",
            )

    def test_create_superuser_rejects_is_superuser_false(self):
        with pytest.raises(ValueError):
            User.objects.create_superuser(
                email="bad2@example.com",
                password=STRONG_PASSWORD,
                is_superuser=False,
                phone_number="0700000003",
                first_name="Bad",
                last_name="Root",
            )

    def test_names_and_str(self, make_user):
        u = make_user(first_name="Jane", last_name="Doe", email="jane@example.com")
        assert u.get_full_name() == "Jane Doe"
        assert u.get_short_name() == "Jane"
        assert str(u) == "jane@example.com"

    def test_is_staff_follows_role(self, make_user):
        assert make_user(role="admin").is_staff is True
        assert make_user(role="user").is_staff is False


class TestUserVerificationModel:
    def test_str(self, user):
        v = UserVerification.objects.create(
            user=user,
            verification_type="email",
            verification_code_hash="x",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        assert str(v) == f"{user.pk} - email"
        assert v.is_verified is False

    def test_cascade_delete(self, user):
        UserVerification.objects.create(
            user=user,
            verification_type="email",
            verification_code_hash="x",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        user.delete()
        assert UserVerification.objects.count() == 0


# ---------------------------------------------------------------------------
# Serializer tests
# ---------------------------------------------------------------------------
class TestUserSerializer:
    def test_never_exposes_password(self, user):
        data = UserSerializer(user).data
        assert "password" not in data
        assert data["email"] == user.email
        assert data["full_name"] == user.get_full_name()

    def test_all_fields_read_only(self, user):
        s = UserSerializer(user, data={"role": "admin", "email": "x@example.com"}, partial=True)
        assert s.is_valid()
        assert s.validated_data == {}


class TestUserVerificationSerializer:
    def test_hides_code_hash(self, user):
        v = UserVerification.objects.create(
            user=user,
            verification_type="email",
            verification_code_hash="secret-hash",
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        data = UserVerificationSerializer(v).data
        assert "verification_code_hash" not in data
        assert data["verification_type"] == "email"


class TestRegisterSerializer:
    def payload(self, **overrides):
        data = {
            "email": "New.User@Example.com",
            "phone_number": "0788111222",
            "first_name": "New",
            "last_name": "User",
            "password": STRONG_PASSWORD,
        }
        data.update(overrides)
        return data

    def test_valid_and_creates_user(self):
        s = RegisterSerializer(data=self.payload())
        assert s.is_valid(), s.errors
        u = s.save()
        assert u.email == "new.user@example.com"
        assert u.role == "user"
        assert u.check_password(STRONG_PASSWORD)

    def test_role_cannot_be_set(self):
        s = RegisterSerializer(data=self.payload(role="admin"))
        assert s.is_valid(), s.errors
        assert s.save().role == "user"

    def test_duplicate_email_case_insensitive(self, make_user):
        make_user(email="taken@example.com")
        s = RegisterSerializer(data=self.payload(email="TAKEN@example.com"))
        assert not s.is_valid()
        assert "email" in s.errors

    def test_duplicate_phone(self, make_user):
        make_user(phone_number="0788111222")
        s = RegisterSerializer(data=self.payload())
        assert not s.is_valid()
        assert "phone_number" in s.errors

    def test_weak_password(self):
        s = RegisterSerializer(data=self.payload(password=WEAK_PASSWORD))
        assert not s.is_valid()
        assert "password" in s.errors

    def test_password_not_in_output(self):
        s = RegisterSerializer(data=self.payload())
        assert s.is_valid()
        s.save()
        assert "password" not in s.data


class TestLoginSerializer:
    def test_valid(self, user):
        s = LoginSerializer(data={"email": user.email.upper(), "password": STRONG_PASSWORD})
        assert s.is_valid(), s.errors
        assert s.validated_data["user"] == user

    def test_wrong_password(self, user):
        s = LoginSerializer(data={"email": user.email, "password": "nope"})
        with pytest.raises(AuthenticationFailed):
            s.is_valid(raise_exception=True)

    def test_unknown_email_same_error(self):
        s = LoginSerializer(data={"email": "ghost@example.com", "password": "nope"})
        with pytest.raises(AuthenticationFailed):
            s.is_valid(raise_exception=True)

    def test_inactive_account(self, make_user):
        u = make_user(is_active=False)
        s = LoginSerializer(data={"email": u.email, "password": STRONG_PASSWORD})
        with pytest.raises(PermissionDenied):
            s.is_valid(raise_exception=True)


class TestVerifyCodeSerializer:
    @pytest.mark.parametrize("code", ["123456", "000000"])
    def test_valid_codes(self, code):
        assert VerifyCodeSerializer(data={"code": code}).is_valid()

    @pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", "12 456", ""])
    def test_invalid_codes(self, code):
        assert not VerifyCodeSerializer(data={"code": code}).is_valid()

    def test_invalid_type(self):
        assert not VerifyCodeSerializer(data={"code": "123456", "verification_type": "fax"}).is_valid()

    def test_default_type_is_email(self):
        s = VerifyCodeSerializer(data={"code": "123456"})
        assert s.is_valid()
        assert s.validated_data["verification_type"] == "email"


class TestProfileUpdateSerializer:
    def test_only_allowed_fields(self, user):
        s = ProfileUpdateSerializer(
            user, data={"first_name": "Zed", "role": "admin", "is_verified": True}, partial=True
        )
        assert s.is_valid(), s.errors
        u = s.save()
        assert u.first_name == "Zed"
        assert u.role == "user"
        assert u.is_verified is False

    def test_duplicate_phone_rejected(self, user, make_user):
        other = make_user()
        s = ProfileUpdateSerializer(user, data={"phone_number": other.phone_number}, partial=True)
        assert not s.is_valid()

    def test_keeping_own_phone_is_ok(self, user):
        s = ProfileUpdateSerializer(user, data={"phone_number": user.phone_number}, partial=True)
        assert s.is_valid(), s.errors


class TestChangePasswordSerializer:
    def ctx(self, user):
        return {"request": SimpleNamespace(user=user)}

    def test_valid_and_save(self, user):
        s = ChangePasswordSerializer(
            data={"old_password": STRONG_PASSWORD, "new_password": OTHER_STRONG_PASSWORD},
            context=self.ctx(user),
        )
        assert s.is_valid(), s.errors
        s.save()
        user.refresh_from_db()
        assert user.check_password(OTHER_STRONG_PASSWORD)

    def test_wrong_old_password(self, user):
        s = ChangePasswordSerializer(
            data={"old_password": "wrong", "new_password": OTHER_STRONG_PASSWORD},
            context=self.ctx(user),
        )
        assert not s.is_valid()
        assert "old_password" in s.errors

    def test_same_password_rejected(self, user):
        s = ChangePasswordSerializer(
            data={"old_password": STRONG_PASSWORD, "new_password": STRONG_PASSWORD},
            context=self.ctx(user),
        )
        assert not s.is_valid()
        assert "new_password" in s.errors

    def test_weak_new_password(self, user):
        s = ChangePasswordSerializer(
            data={"old_password": STRONG_PASSWORD, "new_password": WEAK_PASSWORD},
            context=self.ctx(user),
        )
        assert not s.is_valid()
        assert "new_password" in s.errors


class TestAdminUserUpdateSerializer:
    def ctx(self, user):
        return {"request": SimpleNamespace(user=user)}

    def test_admin_can_update_other_user(self, admin, user):
        s = AdminUserUpdateSerializer(
            user, data={"role": "admin", "is_active": False}, partial=True, context=self.ctx(admin)
        )
        assert s.is_valid(), s.errors
        u = s.save()
        assert u.role == "admin"
        assert u.is_active is False

    def test_cannot_change_own_role(self, admin):
        s = AdminUserUpdateSerializer(admin, data={"role": "user"}, partial=True, context=self.ctx(admin))
        assert not s.is_valid()
        assert "role" in s.errors

    def test_cannot_deactivate_self(self, admin):
        s = AdminUserUpdateSerializer(admin, data={"is_active": False}, partial=True, context=self.ctx(admin))
        assert not s.is_valid()
        assert "is_active" in s.errors

    def test_same_role_on_self_is_allowed(self, admin):
        s = AdminUserUpdateSerializer(admin, data={"role": "admin"}, partial=True, context=self.ctx(admin))
        assert s.is_valid(), s.errors


class TestUserListQuerySerializer:
    def test_defaults(self):
        s = UserListQuerySerializer(data={})
        assert s.is_valid()
        assert s.validated_data["page"] == 1
        assert s.validated_data["page_size"] == 20

    @pytest.mark.parametrize(
        "data",
        [{"page": 0}, {"page_size": 0}, {"page_size": 101}, {"role": "superhero"}],
    )
    def test_invalid(self, data):
        assert not UserListQuerySerializer(data=data).is_valid()


# ---------------------------------------------------------------------------
# View helper tests
# ---------------------------------------------------------------------------
class TestHelpers:
    def test_generate_code_is_six_digits(self):
        for _ in range(50):
            code = views.generate_code()
            assert len(code) == 6 and code.isdigit()

    def test_create_verification_stores_hash_not_code(self, user, sent_codes):
        views.create_verification(user, "email")
        v = UserVerification.objects.get(user=user)
        code = sent_codes[0][2]
        assert v.verification_code_hash != code
        assert views.check_password(code, v.verification_code_hash)
        assert v.expires_at > timezone.now()

    def test_get_tokens_for_user(self, user):
        tokens = views.get_tokens_for_user(user)
        assert set(tokens) == {"refresh", "access"}

    def test_serialize_user_has_no_password(self, user):
        data = views.serialize_user(user)
        assert "password" not in data
        assert data["email"] == user.email


# ---------------------------------------------------------------------------
# RegisterView
# ---------------------------------------------------------------------------
class TestRegisterView:
    def payload(self, **overrides):
        data = {
            "email": "Fresh@Example.com",
            "phone_number": "0788999000",
            "first_name": "Fresh",
            "last_name": "Person",
            "password": STRONG_PASSWORD,
        }
        data.update(overrides)
        return data

    def test_success(self, call, sent_codes):
        resp = call(views.RegisterView, "post", self.payload())
        assert resp.status_code == 201
        assert resp.data["user"]["email"] == "fresh@example.com"
        assert resp.data["user"]["role"] == "user"
        assert "password" not in resp.data["user"]
        assert User.objects.filter(email="fresh@example.com").exists()
        assert UserVerification.objects.filter(verification_type="email").count() == 1
        assert len(sent_codes) == 1

    def test_role_in_body_is_ignored(self, call, sent_codes):
        resp = call(views.RegisterView, "post", self.payload(role="admin"))
        assert resp.status_code == 201
        assert User.objects.get(email="fresh@example.com").role == "user"

    def test_missing_fields(self, call):
        data = self.payload()
        del data["phone_number"]
        del data["last_name"]
        resp = call(views.RegisterView, "post", data)
        assert resp.status_code == 400
        assert set(resp.data["fields"]) == {"phone_number", "last_name"}

    def test_invalid_email(self, call):
        resp = call(views.RegisterView, "post", self.payload(email="not-an-email"))
        assert resp.status_code == 400

    def test_weak_password(self, call):
        resp = call(views.RegisterView, "post", self.payload(password=WEAK_PASSWORD))
        assert resp.status_code == 400
        assert resp.data["errors"]

    def test_duplicate_email(self, call, make_user):
        make_user(email="fresh@example.com")
        resp = call(views.RegisterView, "post", self.payload())
        assert resp.status_code == 409

    def test_duplicate_phone(self, call, make_user):
        make_user(phone_number="0788999000")
        resp = call(views.RegisterView, "post", self.payload())
        assert resp.status_code == 409

    def test_failed_registration_leaves_no_user(self, call, monkeypatch):
        """If sending the code blows up, the transaction must roll back."""

        def boom(*args, **kwargs):
            raise RuntimeError("smtp down")

        monkeypatch.setattr(views, "send_verification_code", boom)
        with pytest.raises(RuntimeError):
            call(views.RegisterView, "post", self.payload())
        assert not User.objects.filter(email="fresh@example.com").exists()


# ---------------------------------------------------------------------------
# LoginView
# ---------------------------------------------------------------------------
class TestLoginView:
    def test_success(self, call, user):
        assert user.last_login is None
        resp = call(views.LoginView, "post", {"email": user.email, "password": STRONG_PASSWORD})
        assert resp.status_code == 200
        assert set(resp.data["tokens"]) == {"refresh", "access"}
        assert resp.data["user"]["id"] == user.id
        user.refresh_from_db()
        assert user.last_login is not None

    def test_email_is_case_insensitive(self, call, user):
        resp = call(views.LoginView, "post", {"email": "  ALICE@Example.com ", "password": STRONG_PASSWORD})
        assert resp.status_code == 200

    def test_wrong_password(self, call, user):
        resp = call(views.LoginView, "post", {"email": user.email, "password": "wrong"})
        assert resp.status_code == 401
        assert resp.data["error"] == "Invalid credentials."

    def test_unknown_email_gives_same_message(self, call, user):
        wrong_pw = call(views.LoginView, "post", {"email": user.email, "password": "wrong"})
        unknown = call(views.LoginView, "post", {"email": "ghost@example.com", "password": "wrong"})
        assert unknown.status_code == wrong_pw.status_code == 401
        assert unknown.data == wrong_pw.data

    def test_inactive_user(self, call, make_user):
        u = make_user(is_active=False)
        resp = call(views.LoginView, "post", {"email": u.email, "password": STRONG_PASSWORD})
        assert resp.status_code == 403

    def test_empty_body(self, call):
        resp = call(views.LoginView, "post", {})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# LogoutView
# ---------------------------------------------------------------------------
class TestLogoutView:
    def test_requires_auth(self, call):
        resp = call(views.LogoutView, "post", {"refresh": "x"})
        assert resp.status_code in (401, 403)

    def test_success_and_token_is_blacklisted(self, call, user):
        refresh = str(RefreshToken.for_user(user))
        resp = call(views.LogoutView, "post", {"refresh": refresh}, user=user)
        assert resp.status_code == 204
        # Using the same token again must fail.
        again = call(views.LogoutView, "post", {"refresh": refresh}, user=user)
        assert again.status_code == 400

    def test_missing_refresh(self, call, user):
        resp = call(views.LogoutView, "post", {}, user=user)
        assert resp.status_code == 400

    def test_garbage_refresh(self, call, user):
        resp = call(views.LogoutView, "post", {"refresh": "not.a.token"}, user=user)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# SendVerificationCodeView
# ---------------------------------------------------------------------------
class TestSendVerificationCodeView:
    def test_requires_auth(self, call):
        assert call(views.SendVerificationCodeView, "post", {}).status_code in (401, 403)

    def test_sends_code(self, call, user, sent_codes):
        resp = call(views.SendVerificationCodeView, "post", {"verification_type": "email"}, user=user)
        assert resp.status_code == 200
        assert UserVerification.objects.filter(user=user, verification_type="email").count() == 1
        assert len(sent_codes) == 1

    def test_defaults_to_email(self, call, user, sent_codes):
        resp = call(views.SendVerificationCodeView, "post", {}, user=user)
        assert resp.status_code == 200
        assert sent_codes[0][1] == "email"

    def test_phone_type(self, call, user, sent_codes):
        resp = call(views.SendVerificationCodeView, "post", {"verification_type": "phone"}, user=user)
        assert resp.status_code == 200
        assert sent_codes[0][1] == "phone"

    def test_invalid_type(self, call, user, sent_codes):
        resp = call(views.SendVerificationCodeView, "post", {"verification_type": "fax"}, user=user)
        assert resp.status_code == 400
        assert sent_codes == []

    def test_already_verified(self, call, make_user, sent_codes):
        u = make_user(is_verified=True)
        resp = call(views.SendVerificationCodeView, "post", {}, user=u)
        assert resp.status_code == 200
        assert "already verified" in resp.data["message"].lower()
        assert sent_codes == []

    def test_rate_limit(self, call, user, sent_codes):
        for _ in range(views.MAX_CODES_PER_HOUR):
            assert call(views.SendVerificationCodeView, "post", {}, user=user).status_code == 200
        resp = call(views.SendVerificationCodeView, "post", {}, user=user)
        assert resp.status_code == 429
        assert len(sent_codes) == views.MAX_CODES_PER_HOUR

    def test_old_codes_do_not_count_toward_limit(self, call, user, sent_codes):
        for _ in range(views.MAX_CODES_PER_HOUR):
            views.create_verification(user, "email")
        UserVerification.objects.filter(user=user).update(created_at=timezone.now() - timedelta(hours=2))
        resp = call(views.SendVerificationCodeView, "post", {}, user=user)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# VerifyCodeView
# ---------------------------------------------------------------------------
class TestVerifyCodeView:
    def test_requires_auth(self, call):
        assert call(views.VerifyCodeView, "post", {"code": "123456"}).status_code in (401, 403)

    def test_success(self, call, user, sent_codes):
        views.create_verification(user, "email")
        code = sent_codes[-1][2]
        resp = call(views.VerifyCodeView, "post", {"verification_type": "email", "code": code}, user=user)
        assert resp.status_code == 200
        assert resp.data["user"]["is_verified"] is True
        user.refresh_from_db()
        assert user.is_verified is True
        assert UserVerification.objects.get(user=user).is_verified is True

    def test_wrong_code(self, call, user, sent_codes):
        views.create_verification(user, "email")
        real = sent_codes[-1][2]
        wrong = "000000" if real != "000000" else "111111"
        resp = call(views.VerifyCodeView, "post", {"code": wrong}, user=user)
        assert resp.status_code == 400
        user.refresh_from_db()
        assert user.is_verified is False

    def test_expired_code(self, call, user, sent_codes):
        views.create_verification(user, "email")
        code = sent_codes[-1][2]
        UserVerification.objects.filter(user=user).update(expires_at=timezone.now() - timedelta(minutes=1))
        resp = call(views.VerifyCodeView, "post", {"code": code}, user=user)
        assert resp.status_code == 400

    def test_code_cannot_be_reused(self, call, user, sent_codes):
        views.create_verification(user, "email")
        code = sent_codes[-1][2]
        assert call(views.VerifyCodeView, "post", {"code": code}, user=user).status_code == 200
        assert call(views.VerifyCodeView, "post", {"code": code}, user=user).status_code == 400

    def test_only_latest_code_is_valid(self, call, user, sent_codes):
        views.create_verification(user, "email")
        old_code = sent_codes[-1][2]
        views.create_verification(user, "email")
        new_code = sent_codes[-1][2]
        if old_code == new_code:  # astronomically unlikely, but avoid a flaky test
            pytest.skip("random codes collided")
        assert call(views.VerifyCodeView, "post", {"code": old_code}, user=user).status_code == 400
        assert call(views.VerifyCodeView, "post", {"code": new_code}, user=user).status_code == 200

    def test_type_must_match(self, call, user, sent_codes):
        views.create_verification(user, "email")
        code = sent_codes[-1][2]
        resp = call(views.VerifyCodeView, "post", {"verification_type": "phone", "code": code}, user=user)
        assert resp.status_code == 400

    def test_cannot_verify_with_another_users_code(self, call, user, make_user, sent_codes):
        other = make_user()
        views.create_verification(other, "email")
        code = sent_codes[-1][2]
        resp = call(views.VerifyCodeView, "post", {"code": code}, user=user)
        assert resp.status_code == 400

    def test_missing_code(self, call, user):
        assert call(views.VerifyCodeView, "post", {}, user=user).status_code == 400

    def test_invalid_type(self, call, user):
        resp = call(views.VerifyCodeView, "post", {"verification_type": "fax", "code": "123456"}, user=user)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# ProfileView
# ---------------------------------------------------------------------------
class TestProfileView:
    def test_requires_auth(self, call):
        assert call(views.ProfileView, "get").status_code in (401, 403)

    def test_get(self, call, user):
        resp = call(views.ProfileView, "get", user=user)
        assert resp.status_code == 200
        assert resp.data["email"] == user.email
        assert "password" not in resp.data

    def test_patch_updates_allowed_fields(self, call, user):
        resp = call(
            views.ProfileView,
            "patch",
            {"first_name": "  Alicia ", "last_name": "Smith", "phone_number": "0788123123"},
            user=user,
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert (user.first_name, user.last_name, user.phone_number) == ("Alicia", "Smith", "0788123123")

    def test_patch_ignores_protected_fields(self, call, user):
        resp = call(
            views.ProfileView,
            "patch",
            {"role": "admin", "is_verified": True, "email": "hacker@example.com", "is_active": False},
            user=user,
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.role == "user"
        assert user.is_verified is False
        assert user.email == "alice@example.com"
        assert user.is_active is True

    def test_patch_empty_value_rejected(self, call, user):
        resp = call(views.ProfileView, "patch", {"first_name": "   "}, user=user)
        assert resp.status_code == 400

    def test_patch_duplicate_phone(self, call, user, make_user):
        other = make_user()
        resp = call(views.ProfileView, "patch", {"phone_number": other.phone_number}, user=user)
        assert resp.status_code == 409

    def test_patch_own_phone_is_fine(self, call, user):
        resp = call(views.ProfileView, "patch", {"phone_number": user.phone_number}, user=user)
        assert resp.status_code == 200

    def test_patch_with_no_fields(self, call, user):
        resp = call(views.ProfileView, "patch", {}, user=user)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# ChangePasswordView
# ---------------------------------------------------------------------------
class TestChangePasswordView:
    def test_requires_auth(self, call):
        assert call(views.ChangePasswordView, "post", {}).status_code in (401, 403)

    def test_success(self, call, user):
        resp = call(
            views.ChangePasswordView,
            "post",
            {"old_password": STRONG_PASSWORD, "new_password": OTHER_STRONG_PASSWORD},
            user=user,
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.check_password(OTHER_STRONG_PASSWORD)
        assert not user.check_password(STRONG_PASSWORD)

    def test_wrong_old_password(self, call, user):
        resp = call(
            views.ChangePasswordView,
            "post",
            {"old_password": "wrong", "new_password": OTHER_STRONG_PASSWORD},
            user=user,
        )
        assert resp.status_code == 400
        user.refresh_from_db()
        assert user.check_password(STRONG_PASSWORD)

    def test_weak_new_password(self, call, user):
        resp = call(
            views.ChangePasswordView,
            "post",
            {"old_password": STRONG_PASSWORD, "new_password": WEAK_PASSWORD},
            user=user,
        )
        assert resp.status_code == 400
        assert resp.data["errors"]
        user.refresh_from_db()
        assert user.check_password(STRONG_PASSWORD)

    def test_missing_fields(self, call, user):
        resp = call(views.ChangePasswordView, "post", {}, user=user)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Admin views: permission
# ---------------------------------------------------------------------------
class TestIsAdminRole:
    def test_anonymous_denied(self, call):
        assert call(views.UserListView, "get").status_code in (401, 403)

    def test_regular_user_denied(self, call, user):
        assert call(views.UserListView, "get", user=user).status_code == 403
        assert call(views.UserDetailView, "get", user=user, pk=user.pk).status_code == 403
        assert call(views.UserDetailView, "patch", {"role": "admin"}, user=user, pk=user.pk).status_code == 403
        assert call(views.UserDetailView, "delete", user=user, pk=user.pk).status_code == 403

    def test_admin_allowed(self, call, admin):
        assert call(views.UserListView, "get", user=admin).status_code == 200


# ---------------------------------------------------------------------------
# UserListView
# ---------------------------------------------------------------------------
class TestUserListView:
    def test_lists_users_with_pagination_metadata(self, call, admin, make_user):
        for _ in range(3):
            make_user()
        resp = call(views.UserListView, "get", user=admin)
        assert resp.status_code == 200
        assert resp.data["count"] == 4  # 3 + admin
        assert resp.data["page"] == 1
        assert resp.data["page_size"] == 20
        assert len(resp.data["results"]) == 4
        assert all("password" not in u for u in resp.data["results"])

    def test_pagination(self, call, admin, make_user):
        for _ in range(4):
            make_user()  # 5 users in total
        page1 = call(views.UserListView, "get", user=admin, query={"page": 1, "page_size": 2})
        page3 = call(views.UserListView, "get", user=admin, query={"page": 3, "page_size": 2})
        assert len(page1.data["results"]) == 2
        assert len(page3.data["results"]) == 1
        assert page1.data["count"] == 5

    def test_page_size_is_capped(self, call, admin):
        resp = call(views.UserListView, "get", user=admin, query={"page_size": 1000})
        assert resp.data["page_size"] == 100

    def test_invalid_pagination(self, call, admin):
        resp = call(views.UserListView, "get", user=admin, query={"page": "abc"})
        assert resp.status_code == 400

    def test_search(self, call, admin, make_user):
        make_user(email="findme@example.com", first_name="Zelda")
        make_user(email="other@example.com", first_name="Link")
        resp = call(views.UserListView, "get", user=admin, query={"search": "zelda"})
        assert [u["email"] for u in resp.data["results"]] == ["findme@example.com"]

    def test_search_by_phone(self, call, admin, make_user):
        make_user(phone_number="0799555444")
        resp = call(views.UserListView, "get", user=admin, query={"search": "555444"})
        assert resp.data["count"] == 1

    def test_filter_by_role(self, call, admin, make_user):
        make_user()
        resp = call(views.UserListView, "get", user=admin, query={"role": "admin"})
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["role"] == "admin"

    def test_filter_by_is_active(self, call, admin, make_user):
        make_user(is_active=False)
        inactive = call(views.UserListView, "get", user=admin, query={"is_active": "false"})
        active = call(views.UserListView, "get", user=admin, query={"is_active": "true"})
        assert inactive.data["count"] == 1
        assert active.data["count"] == 1  # just the admin

    def test_ordered_newest_first(self, call, admin, make_user):
        newest = make_user()
        resp = call(views.UserListView, "get", user=admin)
        assert resp.data["results"][0]["id"] == newest.id


# ---------------------------------------------------------------------------
# UserDetailView
# ---------------------------------------------------------------------------
class TestUserDetailView:
    def test_get(self, call, admin, user):
        resp = call(views.UserDetailView, "get", user=admin, pk=user.pk)
        assert resp.status_code == 200
        assert resp.data["email"] == user.email

    def test_get_not_found(self, call, admin):
        resp = call(views.UserDetailView, "get", user=admin, pk=999999)
        assert resp.status_code == 404

    def test_patch_role_and_flags(self, call, admin, user):
        resp = call(
            views.UserDetailView,
            "patch",
            {"role": "admin", "is_active": False, "is_verified": True},
            user=admin,
            pk=user.pk,
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.role == "admin"
        assert user.is_active is False
        assert user.is_verified is True

    def test_patch_invalid_role(self, call, admin, user):
        resp = call(views.UserDetailView, "patch", {"role": "superhero"}, user=admin, pk=user.pk)
        assert resp.status_code == 400
        user.refresh_from_db()
        assert user.role == "user"

    def test_admin_cannot_change_own_role(self, call, admin):
        resp = call(views.UserDetailView, "patch", {"role": "user"}, user=admin, pk=admin.pk)
        assert resp.status_code == 400
        admin.refresh_from_db()
        assert admin.role == "admin"

    def test_admin_cannot_deactivate_self(self, call, admin):
        resp = call(views.UserDetailView, "patch", {"is_active": False}, user=admin, pk=admin.pk)
        assert resp.status_code == 400
        admin.refresh_from_db()
        assert admin.is_active is True

    def test_admin_can_patch_self_harmlessly(self, call, admin):
        resp = call(views.UserDetailView, "patch", {"role": "admin", "is_verified": True}, user=admin, pk=admin.pk)
        assert resp.status_code == 200

    def test_patch_not_found(self, call, admin):
        resp = call(views.UserDetailView, "patch", {"role": "user"}, user=admin, pk=999999)
        assert resp.status_code == 404

    def test_delete_other_user(self, call, admin, user):
        resp = call(views.UserDetailView, "delete", user=admin, pk=user.pk)
        assert resp.status_code == 204
        assert not User.objects.filter(pk=user.pk).exists()

    def test_admin_cannot_delete_self(self, call, admin):
        resp = call(views.UserDetailView, "delete", user=admin, pk=admin.pk)
        assert resp.status_code == 400
        assert User.objects.filter(pk=admin.pk).exists()

    def test_delete_not_found(self, call, admin):
        resp = call(views.UserDetailView, "delete", user=admin, pk=999999)
        assert resp.status_code == 404