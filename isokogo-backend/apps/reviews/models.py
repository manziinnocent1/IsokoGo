
import uuid

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class ProductReview(models.Model):

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        HIDDEN = 'hidden', 'Hidden'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='product_reviews'
    )

    product = models.ForeignKey(
    "catalog.Product",
    on_delete=models.CASCADE,
    related_name="reviews"
)

    order_item = models.ForeignKey(
        'orders.OrderItem',
        on_delete=models.PROTECT,
        related_name='reviews'
    )

    rating = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5)
        ]
    )

    comment = models.TextField(
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    is_verified_purchase = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        db_table = 'product_reviews'
        verbose_name = 'Product Review'
        verbose_name_plural = 'Product Reviews'
        ordering = ['-created_at']

        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'product', 'order_item'],
                name='unique_customer_product_order_item_review'
            )
        ]

    def __str__(self):
        return f"{self.product} - {self.rating}/5"
