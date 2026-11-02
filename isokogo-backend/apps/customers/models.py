
import uuid

from django.conf import settings
from django.db import models


class CustomerProfile(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile"
    )

    profile_image = models.ImageField(
        upload_to="customers/profile_images/",
        null=True,
        blank=True
    )

    date_of_birth = models.DateField(
        null=True,
        blank=True
    )

    preferred_language = models.CharField(
        max_length=30,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customer_profiles"
        verbose_name = "Customer Profile"
        verbose_name_plural = "Customer Profiles"

    def __str__(self):
        return str(self.user)


class CustomerAddress(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="addresses"
    )

    address_name = models.CharField(
        max_length=100,
        help_text="Example: Home, Office, or Shop"
    )

    recipient_name = models.CharField(max_length=150)
    recipient_phone_number = models.CharField(max_length=20)

    province = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    sector = models.CharField(max_length=100)
    cell = models.CharField(max_length=100)
    village = models.CharField(max_length=100, blank=True)

    street_address = models.CharField(max_length=255)

    delivery_instructions = models.TextField(
        blank=True
    )

    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True
    )

    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True
    )

    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customer_addresses"
        verbose_name = "Customer Address"
        verbose_name_plural = "Customer Addresses"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.address_name} - {self.district}"
