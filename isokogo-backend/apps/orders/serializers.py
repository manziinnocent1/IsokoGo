
from decimal import Decimal

from django.db import transaction
from django.utils.crypto import get_random_string

from rest_framework import serializers

from .models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    OrderSubstitution,
)
from apps.catalog.models import ProductVariant


class OrderItemInputSerializer(serializers.Serializer):
    variant = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.filter(is_active=True)
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "id",
            "order",
            "product",
            "variant",
            "product_name",
            "variant_name",
            "sku",
            "quantity",
            "unit_price",
            "subtotal",
        ]
        read_only_fields = fields


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderStatusHistory
        fields = [
            "id",
            "order",
            "previous_status",
            "new_status",
            "changed_by",
            "changed_by_name",
            "note",
            "created_at",
        ]
        read_only_fields = fields

    def get_changed_by_name(self, obj):
        if not obj.changed_by:
            return None

        return obj.changed_by.get_full_name() or obj.changed_by.get_username()


class OrderSubstitutionSerializer(serializers.ModelSerializer):
    requested_variant_name = serializers.CharField(
        source="requested_variant.name",
        read_only=True,
    )
    suggested_variant_name = serializers.CharField(
        source="suggested_variant.name",
        read_only=True,
    )
    order_number = serializers.CharField(
        source="order_item.order.order_number",
        read_only=True,
    )

    class Meta:
        model = OrderSubstitution
        fields = [
            "id",
            "order_item",
            "order_number",
            "requested_variant",
            "requested_variant_name",
            "suggested_variant",
            "suggested_variant_name",
            "status",
            "customer_response",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "customer_response",
            "created_at",
        ]

    def validate(self, attrs):
        order_item = attrs.get(
            "order_item",
            getattr(self.instance, "order_item", None),
        )
        requested = attrs.get(
            "requested_variant",
            getattr(self.instance, "requested_variant", None),
        )
        suggested = attrs.get(
            "suggested_variant",
            getattr(self.instance, "suggested_variant", None),
        )

        if order_item and requested:
            if order_item.variant_id != requested.id:
                raise serializers.ValidationError({
                    "requested_variant": "This must match the order item's original variant."
                })

        if requested and suggested and requested.id == suggested.id:
            raise serializers.ValidationError({
                "suggested_variant": "Choose a different product variant."
            })

        if suggested and not suggested.is_active:
            raise serializers.ValidationError({
                "suggested_variant": "The suggested variant is inactive."
            })

        return attrs


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    substitutions = OrderSubstitutionSerializer(many=True, read_only=True)

    order_items = OrderItemInputSerializer(
        many=True,
        write_only=True,
        required=True,
    )

    customer_name = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "customer",
            "customer_name",
            "delivery_address",
            "delivery_address_snapshot",
            "status",
            "subtotal",
            "discount_amount",
            "delivery_fee",
            "tax_amount",
            "total_amount",
            "customer_notes",
            "scheduled_delivery",
            "items",
            "order_items",
            "item_count",
            "status_history",
            "substitutions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "order_number",
            "customer",
            "customer_name",
            "delivery_address_snapshot",
            "status",
            "subtotal",
            "discount_amount",
            "delivery_fee",
            "tax_amount",
            "total_amount",
            "items",
            "item_count",
            "status_history",
            "substitutions",
            "created_at",
            "updated_at",
        ]

    def get_customer_name(self, obj):
        return obj.customer.get_full_name() or obj.customer.get_username()

    def get_item_count(self, obj):
        return obj.items.count()

    def validate(self, attrs):
        request = self.context.get("request")
        address = attrs.get("delivery_address")

        if address and request and not request.user.is_staff:
            if address.customer.user_id != request.user.id:
                raise serializers.ValidationError({
                    "delivery_address": "You can only use your own delivery address."
                })

            if not address.is_active:
                raise serializers.ValidationError({
                    "delivery_address": "This delivery address is inactive."
                })

        if not self.initial_data.get("order_items"):
            raise serializers.ValidationError({
                "order_items": "An order must contain at least one item."
            })

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        items_data = validated_data.pop("order_items")

        address = validated_data.get("delivery_address")

        address_snapshot = {}
        if address:
            address_snapshot = {
                "recipient_name": address.recipient_name,
                "recipient_phone": address.recipient_phone,
                "province": address.province,
                "district": address.district,
                "sector": address.sector,
                "cell": address.cell,
                "village": address.village,
                "street_address": address.street_address,
                "delivery_instructions": address.delivery_instructions,
                "latitude": str(address.latitude) if address.latitude is not None else None,
                "longitude": str(address.longitude) if address.longitude is not None else None,
            }

        with transaction.atomic():
            order = Order.objects.create(
                customer=request.user,
                order_number=f"ORD-{get_random_string(12).upper()}",
                delivery_address_snapshot=address_snapshot,
                **validated_data,
            )

            subtotal = Decimal("0.00")

            for item_data in items_data:
                variant = item_data["variant"]
                quantity = item_data["quantity"]

                variant = ProductVariant.objects.select_for_update().select_related(
                    "product"
                ).get(pk=variant.pk)

                product = variant.product

                if not variant.is_active or not product.is_available:
                    raise serializers.ValidationError(
                        f"{product.name} is currently unavailable."
                    )

                item = OrderItem.objects.create(
                    order=order,
                    product=product,
                    variant=variant,
                    product_name=product.name,
                    variant_name=variant.name,
                    sku=variant.sku,
                    quantity=quantity,
                    unit_price=variant.selling_price,
                )

                subtotal += item.subtotal

            order.subtotal = subtotal
            order.total_amount = (
                subtotal
                - order.discount_amount
                + order.delivery_fee
                + order.tax_amount
            )

            if order.total_amount < Decimal("0.00"):
                raise serializers.ValidationError(
                    "The order total cannot be negative."
                )

            order.save(update_fields=[
                "subtotal",
                "total_amount",
                "updated_at",
            ])

            OrderStatusHistory.objects.create(
                order=order,
                previous_status="",
                new_status=Order.Status.PENDING,
                changed_by=request.user,
                note="Order created.",
            )

        return order
