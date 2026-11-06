
from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from .models import CustomerProfile, CustomerAddress


# ==========================================================
# CUSTOMER ADDRESS INLINE
# ==========================================================

class CustomerAddressInline(admin.TabularInline):
    """
    Display customer delivery addresses inside the profile page.
    """

    model = CustomerAddress
    extra = 0

    fields = (
        "address_name",
        "recipient_name",
        "recipient_phone_number",
        "district",
        "sector",
        "is_default",
        "is_active",
    )

    show_change_link = True


# ==========================================================
# CUSTOMER PROFILE ADMIN
# ==========================================================

@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    """
    Admin configuration for customer profiles.
    """

    list_display = (
        "id",
        "customer_email",
        "customer_full_name",
        "customer_phone",
        "date_of_birth",
        "preferred_language",
        "total_addresses",
        "created_at",
    )

    list_filter = (
        "preferred_language",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "user__phone_number",
        "preferred_language",
    )

    ordering = (
        "-created_at",
    )

    list_per_page = 25

    autocomplete_fields = (
        "user",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "profile_image_preview",
        "total_addresses",
    )

    inlines = (
        CustomerAddressInline,
    )

    fieldsets = (
        (
            "Customer Information",
            {
                "fields": (
                    "id",
                    "user",
                    "profile_image",
                    "profile_image_preview",
                    "date_of_birth",
                    "preferred_language",
                ),
            },
        ),
        (
            "Customer Statistics",
            {
                "fields": (
                    "total_addresses",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        return queryset.select_related(
            "user"
        ).annotate(
            address_count=Count("addresses", distinct=True)
        )

    @admin.display(description="Email", ordering="user__email")
    def customer_email(self, obj):
        return obj.user.email

    @admin.display(description="Full Name", ordering="user__first_name")
    def customer_full_name(self, obj):
        return obj.user.get_full_name()

    @admin.display(description="Phone Number", ordering="user__phone_number")
    def customer_phone(self, obj):
        return obj.user.phone_number

    @admin.display(description="Total Addresses", ordering="address_count")
    def total_addresses(self, obj):
        return obj.address_count

    @admin.display(description="Profile Image")
    def profile_image_preview(self, obj):
        if obj.profile_image:
            return format_html(
                '<img src="{}" width="90" height="90" '
                'style="object-fit:cover; border-radius:50%;" />',
                obj.profile_image.url,
            )

        return "No profile image"


# ==========================================================
# CUSTOMER ADDRESS ADMIN
# ==========================================================

@admin.register(CustomerAddress)
class CustomerAddressAdmin(admin.ModelAdmin):
    """
    Admin configuration for customer delivery addresses.
    """

    list_display = (
        "address_name",
        "customer_email",
        "recipient_name",
        "recipient_phone_number",
        "province",
        "district",
        "sector",
        "default_status",
        "active_status",
        "created_at",
    )

    list_filter = (
        "province",
        "district",
        "sector",
        "is_default",
        "is_active",
        "created_at",
    )

    search_fields = (
        "address_name",
        "customer__user__email",
        "customer__user__first_name",
        "customer__user__last_name",
        "recipient_name",
        "recipient_phone_number",
        "province",
        "district",
        "sector",
        "cell",
        "village",
        "street_address",
    )

    autocomplete_fields = (
        "customer",
    )

    ordering = (
        "-created_at",
    )

    list_per_page = 25

    list_editable = (
        "is_active",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "map_coordinates",
    )

    fieldsets = (
        (
            "Customer Information",
            {
                "fields": (
                    "id",
                    "customer",
                ),
            },
        ),
        (
            "Address Information",
            {
                "fields": (
                    "address_name",
                    "recipient_name",
                    "recipient_phone_number",
                    "province",
                    "district",
                    "sector",
                    "cell",
                    "village",
                    "street_address",
                    "delivery_instructions",
                ),
            },
        ),
        (
            "Location Coordinates",
            {
                "fields": (
                    "latitude",
                    "longitude",
                    "map_coordinates",
                ),
            },
        ),
        (
            "Address Settings",
            {
                "fields": (
                    "is_default",
                    "is_active",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    actions = (
        "activate_addresses",
        "deactivate_addresses",
        "mark_as_default",
        "remove_default_status",
    )

    @admin.display(description="Customer", ordering="customer__user__email")
    def customer_email(self, obj):
        return obj.customer.user.email

    @admin.display(description="Default Address")
    def default_status(self, obj):
        if obj.is_default:
            return format_html(
                '<span style="color:green; font-weight:bold;">Default</span>'
            )

        return "No"

    @admin.display(description="Active Status")
    def active_status(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="color:green; font-weight:bold;">Active</span>'
            )

        return format_html(
            '<span style="color:red; font-weight:bold;">Inactive</span>'
        )

    @admin.display(description="Map Coordinates")
    def map_coordinates(self, obj):
        if obj.latitude is not None and obj.longitude is not None:
            return f"{obj.latitude}, {obj.longitude}"

        return "Coordinates not provided"

    @admin.action(description="Activate selected addresses")
    def activate_addresses(self, request, queryset):
        updated = queryset.update(is_active=True)

        self.message_user(
            request,
            f"{updated} address(es) activated.",
        )

    @admin.action(description="Deactivate selected addresses")
    def deactivate_addresses(self, request, queryset):
        updated = queryset.update(is_active=False)

        self.message_user(
            request,
            f"{updated} address(es) deactivated.",
        )

    @admin.action(description="Mark selected addresses as default")
    def mark_as_default(self, request, queryset):
        """
        Set one default address per customer.
        Process each customer separately.
        """

        customer_ids = queryset.values_list(
            "customer_id",
            flat=True,
        ).distinct()

        updated = 0
        skipped = 0

        for customer_id in customer_ids:
            selected_address = queryset.filter(
                customer_id=customer_id,
                is_active=True,
            ).first()

            if not selected_address:
                skipped += 1
                continue

            CustomerAddress.objects.filter(
                customer_id=customer_id,
                is_default=True,
            ).exclude(
                pk=selected_address.pk,
            ).update(
                is_default=False,
            )

            selected_address.is_default = True
            selected_address.save(update_fields=["is_default", "updated_at"])

            updated += 1

        self.message_user(
            request,
            f"{updated} customer default address(es) updated. "
            f"{skipped} customer(s) skipped because no active "
            "selected address was available.",
        )

    @admin.action(description="Remove default status from selected addresses")
    def remove_default_status(self, request, queryset):
        updated = queryset.update(is_default=False)

        self.message_user(
            request,
            f"{updated} address(es) are no longer default.",
        )
