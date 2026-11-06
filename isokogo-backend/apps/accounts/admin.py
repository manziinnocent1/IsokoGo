
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone

from .models import User, UserVerification


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom Django Admin configuration for the application's User model.
    """

    model = User

    # Main user list
    list_display = (
        "email",
        "first_name",
        "last_name",
        "phone_number",
        "role",
        "is_active",
        "is_verified",
        "is_staff",
        "date_joined",
    )

    list_filter = (
        "role",
        "is_active",
        "is_verified",
        "is_superuser",
        "date_joined",
    )

    search_fields = (
        "email",
        "first_name",
        "last_name",
        "phone_number",
    )

    ordering = ("-date_joined",)

    list_per_page = 25

    # Fields displayed when creating a user
    add_fieldsets = (
        (
            "Account Information",
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "phone_number",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                ),
            },
        ),
        (
            "Permissions and Status",
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_verified",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
    )

    # Fields displayed when editing an existing user
    fieldsets = (
        (
            "Personal Information",
            {
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "phone_number",
                ),
            },
        ),
        (
            "Account Security",
            {
                "fields": (
                    "password",
                    "last_login",
                ),
            },
        ),
        (
            "Role and Permissions",
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_verified",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (
            "Account Dates",
            {
                "fields": (
                    "date_joined",
                    "updated_at",
                ),
            },
        ),
    )

    readonly_fields = (
        "date_joined",
        "updated_at",
        "last_login",
    )

    filter_horizontal = (
        "groups",
        "user_permissions",
    )

    actions = (
        "verify_selected_users",
        "unverify_selected_users",
        "activate_selected_users",
        "deactivate_selected_users",
    )

    @admin.action(description="Mark selected users as verified")
    def verify_selected_users(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(
            request,
            f"{updated} user(s) successfully verified.",
        )

    @admin.action(description="Mark selected users as unverified")
    def unverify_selected_users(self, request, queryset):
        updated = queryset.update(is_verified=False)
        self.message_user(
            request,
            f"{updated} user(s) marked as unverified.",
        )

    @admin.action(description="Activate selected users")
    def activate_selected_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f"{updated} user(s) successfully activated.",
        )

    @admin.action(description="Deactivate selected users")
    def deactivate_selected_users(self, request, queryset):
        # Prevent accidental deactivation of the current administrator.
        queryset = queryset.exclude(pk=request.user.pk)

        updated = queryset.update(is_active=False)

        self.message_user(
            request,
            f"{updated} user(s) successfully deactivated.",
        )


@admin.register(UserVerification)
class UserVerificationAdmin(admin.ModelAdmin):
    """
    Admin configuration for email and phone verification records.
    """

    list_display = (
        "user",
        "verification_type",
        "is_verified",
        "expires_at",
        "created_at",
        "verification_status",
    )

    list_filter = (
        "verification_type",
        "is_verified",
        "created_at",
        "expires_at",
    )

    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "user__phone_number",
    )

    ordering = ("-created_at",)

    list_per_page = 25

    readonly_fields = (
        "user",
        "verification_type",
        "verification_code_hash",
        "expires_at",
        "created_at",
    )

    fieldsets = (
        (
            "User Information",
            {
                "fields": (
                    "user",
                    "verification_type",
                ),
            },
        ),
        (
            "Verification Details",
            {
                "fields": (
                    "verification_code_hash",
                    "is_verified",
                    "expires_at",
                ),
            },
        ),
        (
            "Record Information",
            {
                "fields": (
                    "created_at",
                ),
            },
        ),
    )

    @admin.display(description="Status")
    def verification_status(self, obj):
        if obj.is_verified:
            return "Verified"

        if obj.expires_at < timezone.now():
            return "Expired"

        return "Pending"

    def has_add_permission(self, request):
        # Verification records should be generated by the application.
        return False

    def has_delete_permission(self, request, obj=None):
        # Preserve verification history.
        return False
