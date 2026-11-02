import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Cart(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CONVERTED = "CONVERTED", "Converted"
        ABANDONED = "ABANDONED", "Abandoned"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="carts",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "carts"
        verbose_name = "Cart"
        verbose_name_plural = "Carts"
        constraints = [
            # A customer can only have one ACTIVE cart at a time
            models.UniqueConstraint(
                fields=["customer"],
                condition=models.Q(status="ACTIVE"),
                name="unique_active_cart_per_customer",
            ),
        ]

    def __str__(self):
        return f"Cart {self.id} ({self.status})"


class CartItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
    )
    # Replace "products.ProductVariant" with your real app label and model name
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="cart_items",
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cart_items"
        verbose_name = "Cart Item"
        verbose_name_plural = "Cart Items"
        constraints = [
            # The same variant can't appear twice in one cart; increase quantity instead
            models.UniqueConstraint(fields=["cart", "variant"], name="unique_variant_per_cart"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.variant_id} in cart {self.cart_id}"