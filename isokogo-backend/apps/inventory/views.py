
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum, Q
from django.shortcuts import get_object_or_404

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Warehouse,
    Stock,
    StockMovement,
    Supplier,
    PurchaseOrder,
    PurchaseOrderItem,
)

from .serializers import (
    WarehouseSerializer,
    StockSerializer,
    StockMovementSerializer,
    SupplierSerializer,
    PurchaseOrderSerializer,
    PurchaseOrderItemSerializer,
)


class StaffWritePermission:
    """
    Allow authenticated users to read.
    Only staff users can create, update, or delete records.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True

        return request.user.is_staff


class StaffOnlyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, StaffWritePermission]


class WarehouseViewSet(StaffOnlyViewSet):
    serializer_class = WarehouseSerializer
    queryset = Warehouse.objects.all().order_by("name")

    def get_queryset(self):
        queryset = super().get_queryset()

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset


class StockViewSet(StaffOnlyViewSet):
    serializer_class = StockSerializer
    queryset = Stock.objects.select_related(
        "variant",
        "warehouse",
    ).all()

    def get_queryset(self):
        queryset = super().get_queryset()

        warehouse_id = self.request.query_params.get("warehouse")
        variant_id = self.request.query_params.get("variant")
        low_stock = self.request.query_params.get("low_stock")

        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)

        if variant_id:
            queryset = queryset.filter(variant_id=variant_id)

        if low_stock and low_stock.lower() == "true":
            queryset = queryset.filter(
                quantity_on_hand__gte=F("quantity_reserved")
            ).annotate(
                available_quantity=F("quantity_on_hand") - F("quantity_reserved")
            ).filter(
                available_quantity__lte=F("reorder_level")
            )

        return queryset

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        """
        Adjust stock and create an audit movement in one transaction.

        Example:
        {
            "movement_type": "ADJUSTMENT",
            "quantity": "10.00",
            "reason": "Physical stock count"
        }

        Quantity is signed:
        positive = add stock
        negative = remove stock
        """
        if not request.user.is_staff:
            raise PermissionDenied(
                "Only staff can adjust stock."
            )

        movement_type = request.data.get("movement_type")
        quantity_value = request.data.get("quantity")
        reference = request.data.get("reference", "")
        reason = request.data.get("reason", "")

        allowed_types = {
            StockMovement.MovementType.PURCHASE,
            StockMovement.MovementType.RETURN,
            StockMovement.MovementType.ADJUSTMENT,
            StockMovement.MovementType.DAMAGE,
            StockMovement.MovementType.EXPIRY,
            StockMovement.MovementType.TRANSFER,
            StockMovement.MovementType.SALE,
        }

        if movement_type not in allowed_types:
            raise ValidationError({
                "movement_type": "Invalid stock movement type."
            })

        try:
            quantity = Decimal(str(quantity_value))
        except (TypeError, ValueError):
            raise ValidationError({
                "quantity": "Provide a valid decimal quantity."
            })

        if quantity == Decimal("0.00"):
            raise ValidationError({
                "quantity": "Quantity cannot be zero."
            })

        if len(str(reference)) > 100:
            raise ValidationError({
                "reference": "Reference cannot exceed 100 characters."
            })

        with transaction.atomic():
            stock = Stock.objects.select_for_update().get(pk=pk)

            new_quantity = stock.quantity_on_hand + quantity

            if new_quantity < stock.quantity_reserved:
                raise ValidationError({
                    "quantity": (
                        "This adjustment would reduce stock below the "
                        "quantity already reserved."
                    )
                })

            stock.quantity_on_hand = new_quantity
            stock.save(update_fields=[
                "quantity_on_hand",
                "updated_at",
            ])

            movement = StockMovement.objects.create(
                stock=stock,
                movement_type=movement_type,
                quantity=quantity,
                reference=reference,
                reason=reason,
                performed_by=request.user,
            )

        return Response({
            "message": "Stock adjusted successfully.",
            "stock": StockSerializer(stock).data,
            "movement": StockMovementSerializer(movement).data,
        }, status=status.HTTP_200_OK)


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated]
    queryset = StockMovement.objects.select_related(
        "stock",
        "stock__variant",
        "stock__warehouse",
        "performed_by",
    ).all()

    def get_queryset(self):
        if not self.request.user.is_staff:
            return StockMovement.objects.none()

        queryset = super().get_queryset()

        stock_id = self.request.query_params.get("stock")
        movement_type = self.request.query_params.get("movement_type")
        warehouse_id = self.request.query_params.get("warehouse")

        if stock_id:
            queryset = queryset.filter(stock_id=stock_id)

        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)

        if warehouse_id:
            queryset = queryset.filter(stock__warehouse_id=warehouse_id)

        return queryset


class SupplierViewSet(StaffOnlyViewSet):
    serializer_class = SupplierSerializer
    queryset = Supplier.objects.all().order_by("name")

    def get_queryset(self):
        queryset = super().get_queryset()

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset


class PurchaseOrderViewSet(StaffOnlyViewSet):
    serializer_class = PurchaseOrderSerializer
    queryset = PurchaseOrder.objects.select_related(
        "supplier",
        "warehouse",
        "created_by",
    ).prefetch_related(
        "items",
        "items__variant",
    ).all()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        purchase_order = self.get_object()

        if purchase_order.status != PurchaseOrder.Status.DRAFT:
            raise ValidationError(
                "Only draft purchase orders can be edited."
            )

        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        purchase_order = self.get_object()

        if purchase_order.status != PurchaseOrder.Status.DRAFT:
            raise ValidationError(
                "Only draft purchase orders can be edited."
            )

        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """
        Submit a draft purchase order for supplier fulfillment.
        """
        with transaction.atomic():
            purchase_order = PurchaseOrder.objects.select_for_update().get(
                pk=pk
            )

            if purchase_order.status != PurchaseOrder.Status.DRAFT:
                raise ValidationError(
                    "Only draft purchase orders can be submitted."
                )

            if not purchase_order.items.exists():
                raise ValidationError(
                    "Add at least one item before submitting this purchase order."
                )

            purchase_order.status = PurchaseOrder.Status.SUBMITTED
            purchase_order.save(update_fields=[
                "status",
                "updated_at",
            ])

        return Response(
            PurchaseOrderSerializer(purchase_order).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        """
        Receive all outstanding items in a submitted purchase order.

        This implementation supports full receipt only. Your current
        PurchaseOrderItem model does not have a received_quantity field,
        so it cannot accurately track partial quantities.
        """
        with transaction.atomic():
            purchase_order = PurchaseOrder.objects.select_for_update().get(
                pk=pk
            )

            if purchase_order.status not in (
                PurchaseOrder.Status.SUBMITTED,
                PurchaseOrder.Status.PARTIALLY_RECEIVED,
            ):
                raise ValidationError(
                    "Only submitted or partially received orders can be received."
                )

            items = list(
                PurchaseOrderItem.objects.select_related(
                    "variant"
                ).filter(
                    purchase_order=purchase_order
                )
            )

            if not items:
                raise ValidationError(
                    "This purchase order has no items."
                )

            for item in items:
                stock, _ = Stock.objects.get_or_create(
                    variant=item.variant,
                    warehouse=purchase_order.warehouse,
                    defaults={
                        "quantity_on_hand": Decimal("0.00"),
                        "quantity_reserved": Decimal("0.00"),
                        "reorder_level": Decimal("0.00"),
                    },
                )

                stock = Stock.objects.select_for_update().get(pk=stock.pk)

                stock.quantity_on_hand += item.quantity
                stock.save(update_fields=[
                    "quantity_on_hand",
                    "updated_at",
                ])

                StockMovement.objects.create(
                    stock=stock,
                    movement_type=StockMovement.MovementType.PURCHASE,
                    quantity=item.quantity,
                    reference=purchase_order.reference_number,
                    reason="Goods received against purchase order.",
                    performed_by=request.user,
                )

            purchase_order.status = PurchaseOrder.Status.RECEIVED
            purchase_order.save(update_fields=[
                "status",
                "updated_at",
            ])

        return Response({
            "message": "Purchase order received and stock updated successfully.",
            "purchase_order": PurchaseOrderSerializer(purchase_order).data,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            purchase_order = PurchaseOrder.objects.select_for_update().get(
                pk=pk
            )

            if purchase_order.status not in (
                PurchaseOrder.Status.DRAFT,
                PurchaseOrder.Status.SUBMITTED,
            ):
                raise ValidationError(
                    "Only draft or submitted purchase orders can be cancelled."
                )

            purchase_order.status = PurchaseOrder.Status.CANCELLED
            purchase_order.save(update_fields=[
                "status",
                "updated_at",
            ])

        return Response(
            PurchaseOrderSerializer(purchase_order).data,
            status=status.HTTP_200_OK,
        )


class PurchaseOrderItemViewSet(StaffOnlyViewSet):
    serializer_class = PurchaseOrderItemSerializer
    queryset = PurchaseOrderItem.objects.select_related(
        "purchase_order",
        "variant",
    ).all()

    def get_queryset(self):
        queryset = super().get_queryset()

        purchase_order_id = self.request.query_params.get("purchase_order")
        if purchase_order_id:
            queryset = queryset.filter(
                purchase_order_id=purchase_order_id
            )

        return queryset

    def perform_create(self, serializer):
        with transaction.atomic():
            purchase_order = PurchaseOrder.objects.select_for_update().get(
                pk=serializer.validated_data["purchase_order"].pk
            )

            if purchase_order.status != PurchaseOrder.Status.DRAFT:
                raise ValidationError(
                    "Items can only be added to draft purchase orders."
                )

            item = serializer.save()
            self.recalculate_total(purchase_order)

    def perform_update(self, serializer):
        with transaction.atomic():
            purchase_order = PurchaseOrder.objects.select_for_update().get(
                pk=serializer.instance.purchase_order_id
            )

            if purchase_order.status != PurchaseOrder.Status.DRAFT:
                raise ValidationError(
                    "Items can only be changed in draft purchase orders."
                )

            serializer.save()
            self.recalculate_total(purchase_order)

    def perform_destroy(self, instance):
        with transaction.atomic():
            purchase_order = PurchaseOrder.objects.select_for_update().get(
                pk=instance.purchase_order_id
            )

            if purchase_order.status != PurchaseOrder.Status.DRAFT:
                raise ValidationError(
                    "Items can only be deleted from draft purchase orders."
                )

            instance.delete()
            self.recalculate_total(purchase_order)

    @staticmethod
    def recalculate_total(purchase_order):
        total = purchase_order.items.aggregate(
            total=Sum("subtotal")
        )["total"] or Decimal("0.00")

        purchase_order.total_amount = total
        purchase_order.save(update_fields=[
            "total_amount",
            "updated_at",
        ])
