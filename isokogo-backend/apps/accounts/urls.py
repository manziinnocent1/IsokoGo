from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    ProfileView,
    RegisterView,
    SendVerificationCodeView,
    UserDetailView,
    UserListView,
    VerifyCodeView,
)

app_name = "accounts"

urlpatterns = [
    # Authentication
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),

    # Verification
    path("verification/send/", SendVerificationCodeView.as_view(), name="verification-send"),
    path("verification/verify/", VerifyCodeView.as_view(), name="verification-verify"),

    # Current user
    path("me/", ProfileView.as_view(), name="profile"),
    path("me/change-password/", ChangePasswordView.as_view(), name="change-password"),

    # Admin
    path("users/", UserListView.as_view(), name="user-list"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
]