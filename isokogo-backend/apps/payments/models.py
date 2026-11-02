
import uuid

from django.db import models
from django.conf import settings


class Payment(models.Model):

    class Provider(models.TextChoices):
        PAYPACK = 'paypack', 'Paypack'
        MTN_MOMO = 'mtn_momo', 'MTN Mobile Money'
        AIRTEL_MONEY = 'airtel_money', 'Airtel Money'
        STRIPE = 'stripe', 'Stripe'
        OTHER = 'other', 'Other'

    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Cash'
        MOBILE_MONEY = 'mobile_money', 'Mobile Money'
        CARD = 'card', 'Card'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        SUCCESSFUL = 'successful', 'Successful'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'
        REFUNDED = 'refunded', 'Refunded'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.PROTECT,
        related_name='payments'
    )

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='payments'
    )

    payment_reference = models.CharField(
        max_length=100,
        unique=True
    )

    provider = models.CharField(
        max_length=30,
        choices=Provider.choices,
        default=Provider.OTHER
    )

    payment_method = models.CharField(
        max_length=30,
        choices=PaymentMethod.choices
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    currency = models.CharField(
        max_length=3,
        default='RWF'
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    transaction_id = models.CharField(
        max_length=150,
        null=True,
        blank=True
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.payment_reference} - {self.status}"


class PaymentTransaction(models.Model):

    class Status(models.TextChoices):
        INITIATED = 'initiated', 'Initiated'
        PENDING = 'pending', 'Pending'
        SUCCESSFUL = 'successful', 'Successful'
        FAILED = 'failed', 'Failed'
        REVERSED = 'reversed', 'Reversed'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name='transactions'
    )

    provider_transaction_id = models.CharField(
        max_length=150,
        null=True,
        blank=True
    )

    request_payload = models.JSONField(
        default=dict,
        blank=True
    )

    response_payload = models.JSONField(
        default=dict,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INITIATED
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_transactions'
        verbose_name = 'Payment Transaction'
        verbose_name_plural = 'Payment Transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.payment.payment_reference} - {self.status}"
