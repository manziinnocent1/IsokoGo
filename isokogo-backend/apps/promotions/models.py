
import uuid

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class Coupon(models.Model):

    class DiscountType(models.TextChoices):
        PERCENTAGE = 'percentage', 'Percentage'
        FIXED = 'fixed', 'Fixed Amount'
        FREE_DELIVERY = 'free_delivery', 'Free Delivery'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    discount_type = models.CharField(
        max_length=20,
        choices=DiscountType.choices
    )

    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )

    minimum_order_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )

    maximum_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)]
    )

    usage_limit = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    usage_per_customer = models.PositiveIntegerField(
        default=1
    )

    start_date = models.DateTimeField()

    expiry_date = models.DateTimeField()

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'coupons'
        verbose_name = 'Coupon'
        verbose_name_plural = 'Coupons'
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    @property
    def is_valid(self):
        now = timezone.now()

        return (
            self.is_active
            and self.start_date <= now <= self.expiry_date
        )


class CouponUsage(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.PROTECT,
        related_name='usages'
    )

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='coupon_usages'
    )

    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.PROTECT,
        related_name='coupon_usages'
    )

    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )

    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'coupon_usages'
        verbose_name = 'Coupon Usage'
        verbose_name_plural = 'Coupon Usages'
        ordering = ['-used_at']

        constraints = [
            models.UniqueConstraint(
                fields=['coupon', 'order'],
                name='unique_coupon_per_order'
            )
        ]

    def __str__(self):
        return f"{self.coupon.code} - {self.customer_id}"


class Promotion(models.Model):

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SCHEDULED = 'scheduled', 'Scheduled'
        ACTIVE = 'active', 'Active'
        EXPIRED = 'expired', 'Expired'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    name = models.CharField(
        max_length=150
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    banner_image = models.ImageField(
        upload_to='promotions/banners/',
        blank=True,
        null=True
    )

    start_date = models.DateTimeField()

    end_date = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'promotions'
        verbose_name = 'Promotion'
        verbose_name_plural = 'Promotions'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def is_currently_active(self):
        now = timezone.now()

        return (
            self.is_active
            and self.status == self.Status.ACTIVE
            and self.start_date <= now <= self.end_date
        )
