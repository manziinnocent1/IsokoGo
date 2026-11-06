
from decimal import Decimal

from rest_framework import serializers

from .models import (
    Warehouse,
    Stock,
    StockMovement,
    Supplier,
    PurchaseOrder,
    PurchaseOrderItem,
)


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = [
            "id",
            "name",
            "address",
            "contact_phone",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class StockSerializer(serializers.ModelSerializer):
    variant_name = serializers.CharField(
        source="variant.name",
        read_only=True,
    )
    warehouse_name = serializers.CharField(
        source="warehouse.name",
        read_only=True,
    )
    quantity_available = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    needs_reorder = serializers.BooleanField(read_only=True)

    class Meta:
        model = Stock
        fields = [
            "id",
            "variant",
            "variant_name",
            "warehouse",
            "warehouse_name",
            "quantity_on_hand",
            "quantity_reserved",
            "quantity_available",
            "reorder_level",
            "needs_reorder",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "quantity_on_hand",
            "quantity_reserved",
            "quantity_available",
            "needs_reorder",
            "updated_at",
        ]

    def validate(self, attrs):
        variant = attrs.get("variant", getattr(self.instance, "variant", None))
        warehouse = attrs.get("warehouse", getattr(self.instance, "warehouse", None))

        if variant and warehouse:
            queryset = Stock.objects.filter(
                variant=variant,
                warehouse=warehouse,
            )
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                raise serializers.ValidationError(
                    "A stock record already exists for this variant and warehouse."
                )

        return attrs


class StockMovementSerializer(serializers.ModelSerializer):
    variant_name = serializers.CharField(
        source="stock.variant.name",
        read_only=True,
    )
    warehouse_name = serializers.CharField(
        source="stock.warehouse.name",
        read_only=True,
    )
    performed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "stock",
            "variant_name",
            "warehouse_name",
            "movement_type",
            "quantity",
            "reference",
            "reason",
            "performed_by",
            "performed_by_name",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "performed_by",
            "created_at",
        ]

    def get_performed_by_name(self, obj):
        if not obj.performed_by:
            return None

        return (
            obj.performed_by.get_full_name()
            or obj.performed_by.get_username()
        )


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "contact_person",
            "email",
            "address",
            "is_active",
        ]
        read_only_fields = ["id"]


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    variant_name = serializers.CharField(
        source="variant.name",
        read_only=True,
    )
    variant_sku = serializers.CharField(
        source="variant.sku",
        read_only=True,
    )

    class Meta:
        model = PurchaseOrderItem
        fields = [
            "id",
            "purchase_order",
            "variant",
            "variant_name",
            "variant_sku",
            "quantity",
            "unit_cost",
            "subtotal",
        ]
        read_only_fields = ["id", "subtotal"]

    def validate(self, attrs):
        purchase_order = attrs.get(
            "purchase_order",
            getattr(self.instance, "purchase_order", None),
        )

        if purchase_order and purchase_order.status != PurchaseOrder.Status.DRAFT:
            raise serializers.ValidationError(
                "Items can only be changed while the purchase order is in DRAFT status."
            )

        return attrs

    def validate_quantity(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError(
                "Quantity must be greater than zero."
            )
        return value

    def validate_unit_cost(self, value):
        if value < Decimal("0.00"):
            raise serializers.ValidationError(
                "Unit cost cannot be negative."
            )
        return value


class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(
        source="supplier.name",
        read_only=True,
    )
    warehouse_name = serializers.CharField(
        source="warehouse.name",
        read_only=True,
    )
    created_by_name = serializers.SerializerMethodField()
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "supplier",
            "supplier_name",
            "warehouse",
            "warehouse_name",
            "reference_number",
            "status",
            "total_amount",
            "expected_delivery",
            "created_by",
            "created_by_name",
            "items",
            "item_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "total_amount",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None

        return (
            obj.created_by.get_full_name()
            or obj.created_by.get_username()
        )

    def get_item_count(self, obj):
        return obj.items.count()

    def validate(self, attrs):
        supplier = attrs.get(
            "supplier",
            getattr(self.instance, "supplier", None),
        )
        warehouse = attrs.get(
            "warehouse",
            getattr(self.instance, "warehouse", None),
        )

        if supplier and not supplier.is_active:
            raise serializers.ValidationError(
                {"supplier": "This supplier is inactive."}
            )

        if warehouse and not warehouse.is_active:
            raise serializers.ValidationError(
                {"warehouse": "This warehouse is inactive."}
            )

        return attrs
