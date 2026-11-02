import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        ORDER_PLACED = "ORDER_PLACED", "Order placed"
        ORDER_CONFIRMED = "ORDER_CONFIRMED", "Order confirmed"
        ORDER_CANCELLED = "ORDER_CANCELLED", "Order cancelled"
        PAYMENT = "PAYMENT", "Payment"
        DELIVERY_ASSIGNED = "DELIVERY_ASSIGNED", "Delivery assigned"
        DELIVERY_UPDATE = "DELIVERY_UPDATE", "Delivery update"
        PROMOTION = "PROMOTION", "Promotion"
        SYSTEM = "SYSTEM", "System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
    )
    is_read = models.BooleanField(default=False)
    # Replace "orders.Order" with your real app label and model name.
    # Optional: not every notification is about an order.
    related_order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]
        indexes = [
            # Fast "unread notifications for this user" lookups
            models.Index(fields=["recipient", "is_read", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} -> {self.recipient_id}"