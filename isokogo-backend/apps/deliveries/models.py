import uuid

from django.conf import settings
from django.db import models


class DeliveryPersonnel(models.Model):
    class VehicleType(models.TextChoices):
        MOTORCYCLE = "MOTORCYCLE", "Motorcycle"
        BICYCLE = "BICYCLE", "Bicycle"
        CAR = "CAR", "Car"
        VAN = "VAN", "Van"

    class AvailabilityStatus(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        BUSY = "BUSY", "Busy"
        OFFLINE = "OFFLINE", "Offline"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="delivery_profile",
    )
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices)
    # blank=True because bicycles and similar have no registration plate
    vehicle_registration = models.CharField(max_length=30, blank=True)
    availability_status = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.OFFLINE,
    )
    is_verified = models.BooleanField(default=False)

    class Meta:
        db_table = "delivery_personnel"
        verbose_name = "Delivery Personnel"
        verbose_name_plural = "Delivery Personnel"

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.vehicle_type})"


class DeliveryZone(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    province = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    base_delivery_fee = models.DecimalField(max_digits=10, decimal_places=2)
    estimated_delivery_minutes = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "delivery_zones"
        verbose_name = "Delivery Zone"
        verbose_name_plural = "Delivery Zones"
        constraints = [
            models.UniqueConstraint(fields=["name", "district"], name="unique_zone_name_per_district"),
        ]

    def __str__(self):
        return f"{self.name} ({self.district})"


class Delivery(models.Model):
    class Status(models.TextChoices):
        PENDING_ASSIGNMENT = "PENDING_ASSIGNMENT", "Pending assignment"
        ASSIGNED = "ASSIGNED", "Assigned"
        PICKED_UP = "PICKED_UP", "Picked up"
        IN_TRANSIT = "IN_TRANSIT", "In transit"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Replace "orders.Order" with your real app label and model name
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="delivery",
    )
    # Null until a courier is assigned
    delivery_personnel = models.ForeignKey(
        DeliveryPersonnel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries",
    )
    delivery_zone = models.ForeignKey(
        DeliveryZone,
        on_delete=models.PROTECT,
        related_name="deliveries",
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING_ASSIGNMENT,
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2)
    recipient_name = models.CharField(max_length=100)
    recipient_phone = models.CharField(max_length=15)
    proof_of_delivery = models.ImageField(upload_to="delivery_proofs/", null=True, blank=True)
    delivery_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "deliveries"
        verbose_name = "Delivery"
        verbose_name_plural = "Deliveries"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Delivery {self.id} ({self.status})"


class DeliveryTracking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery = models.ForeignKey(
        Delivery,
        on_delete=models.CASCADE,
        related_name="tracking_events",
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "delivery_tracking"
        verbose_name = "Delivery Tracking"
        verbose_name_plural = "Delivery Tracking"
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(fields=["delivery", "-recorded_at"]),
        ]

    def __str__(self):
        return f"Tracking {self.delivery_id} @ {self.recorded_at}"