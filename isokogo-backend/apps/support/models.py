
import uuid

from django.db import models
from django.conf import settings
from django.core.validators import MinLengthValidator


class SupportTicket(models.Model):

    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        URGENT = 'urgent', 'Urgent'

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        IN_PROGRESS = 'in_progress', 'In Progress'
        WAITING_CUSTOMER = 'waiting_customer', 'Waiting for Customer'
        RESOLVED = 'resolved', 'Resolved'
        CLOSED = 'closed', 'Closed'

    class Category(models.TextChoices):
        GENERAL = 'general', 'General Inquiry'
        ORDER = 'order', 'Order Issue'
        PAYMENT = 'payment', 'Payment Issue'
        DELIVERY = 'delivery', 'Delivery Issue'
        REFUND = 'refund', 'Refund Request'
        PRODUCT = 'product', 'Product Issue'
        ACCOUNT = 'account', 'Account Issue'
        OTHER = 'other', 'Other'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    ticket_number = models.CharField(
        max_length=30,
        unique=True,
        editable=False
    )

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='support_tickets'
    )

    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_tickets'
    )

    subject = models.CharField(
        max_length=200
    )

    description = models.TextField(
        validators=[MinLengthValidator(10)]
    )

    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.GENERAL
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.OPEN
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_support_tickets'
    )

    resolution_notes = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'support_tickets'
        verbose_name = 'Support Ticket'
        verbose_name_plural = 'Support Tickets'
        ordering = ['-created_at']

        indexes = [
            models.Index(fields=['ticket_number']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['priority', 'created_at']),
        ]

    def __str__(self):
        return f"{self.ticket_number} - {self.subject}"

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            self.ticket_number = (
                f"ISO-{uuid.uuid4().hex[:10].upper()}"
            )

        super().save(*args, **kwargs)
