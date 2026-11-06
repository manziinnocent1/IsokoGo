
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    OrderSubstitution,
)

from .serializers import (
    OrderSerializer,
    OrderItemSerializer,
    OrderStatusHistorySerializer,
    OrderSubstitutionSerializer,
)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    queryset = Order.objects.select_related(
        "customer",
        "delivery_address",
    ).prefetch_related(
        "items",
        "status_history",
        "substitutions",
    ).all()

    def get_queryset(self):
        queryset = super().get_queryset()

        if not self.request.user.is_staff:
            queryset = queryset.filter(customer=self.request.user)

        order_status = self.request.query_params.get("status")
        if order_status:
            queryset = queryset.filter(status=order_status)

        return queryset

    def perform_update(self, serializer):
        raise PermissionDenied(
            "Orders cannot be edited directly. Use the appropriate order actions."
        )

    def destroy(self, request, *args, **kwargs):
        raise PermissionDenied(
            "Orders cannot be deleted. Cancel the order instead."
        )

    @action(detail=True, methods=["post"])
    def update_status(self, request, pk=None):
        if not request.user.is_staff:
            raise PermissionDenied(
                "Only staff members can update order statuses."
            )

        new_status = request.data.get("status")
        note = request.data.get("note", "")

        allowed_transitions = {
            Order.Status.PENDING: [
                Order.Status.CONFIRMED,
                Order.Status.CANCELLED,
            ],
            Order.Status.CONFIRMED: [
                Order.Status.PREPARING,
                Order.Status.CANCELLED,
            ],
            Order.Status.PREPARING: [
                Order.Status.READY_FOR_DELIVERY,
                Order.Status.CANCELLED,
            ],
            Order.Status.READY_FOR_DELIVERY: [
                Order.Status.OUT_FOR_DELIVERY,
                Order.Status.CANCELLED,
            ],
            Order.Status.OUT_FOR_DELIVERY: [
                Order.Status.DELIVERED,
            ],
            Order.Status.DELIVERED: [],
            Order.Status.CANCELLED: [],
            Order.Status.REFUNDED: [],
        }

        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=pk)

            if new_status not in Order.Status.values:
                raise ValidationError({
                    "status": "Invalid order status."
                })

            if new_status not in allowed_transitions[order.status]:
                raise ValidationError({
                    "status": (
                        f"Cannot change order from {order.status} "
                        f"to {new_status}."
                    )
                })

            previous_status = order.status
            order.status = new_status
            order.save(update_fields=["status", "updated_at"])

            OrderStatusHistory.objects.create(
                order=order,
                previous_status=previous_status,
                new_status=new_status,
                changed_by=request.user,
                note=note,
            )

        return Response(OrderSerializer(order, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=pk)

            if not request.user.is_staff and order.customer_id != request.user.id:
                raise PermissionDenied("You cannot cancel this order.")

            if order.status not in [
                Order.Status.PENDING,
                Order.Status.CONFIRMED,
            ]:
                raise ValidationError(
                    "This order can no longer be cancelled."
                )

            previous_status = order.status
            order.status = Order.Status.CANCELLED
            order.save(update_fields=["status", "updated_at"])

            OrderStatusHistory.objects.create(
                order=order,
                previous_status=previous_status,
                new_status=Order.Status.CANCELLED,
                changed_by=request.user,
                note=request.data.get("note", "Order cancelled."),
            )

        return Response({
            "message": "Order cancelled successfully.",
            "order": OrderSerializer(
                order,
                context=self.get_serializer_context(),
            ).data,
        })


class OrderItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderItemSerializer
    permission_classes = [IsAuthenticated]

    queryset = OrderItem.objects.select_related(
        "order",
        "product",
        "variant",
    ).all()

    def get_queryset(self):
        queryset = super().get_queryset()

        if not self.request.user.is_staff:
            queryset = queryset.filter(order__customer=self.request.user)

        order_id = self.request.query_params.get("order")
        if order_id:
            queryset = queryset.filter(order_id=order_id)

        return queryset


class OrderStatusHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderStatusHistorySerializer
    permission_classes = [IsAuthenticated]

    queryset = OrderStatusHistory.objects.select_related(
        "order",
        "changed_by",
    ).all()

    def get_queryset(self):
        queryset = super().get_queryset()

        if not self.request.user.is_staff:
            queryset = queryset.filter(order__customer=self.request.user)

        order_id = self.request.query_params.get("order")
        if order_id:
            queryset = queryset.filter(order_id=order_id)

        return queryset


class OrderSubstitutionViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSubstitutionSerializer
    permission_classes = [IsAuthenticated]

    queryset = OrderSubstitution.objects.select_related(
        "order_item",
        "order_item__order",
        "requested_variant",
        "suggested_variant",
    ).all()

    def get_queryset(self):
        queryset = super().get_queryset()

        if not self.request.user.is_staff:
            queryset = queryset.filter(
                order_item__order__customer=self.request.user
            )

        substitution_status = self.request.query_params.get("status")
        if substitution_status:
            queryset = queryset.filter(status=substitution_status)

        return queryset

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied(
                "Only staff can propose product substitutions."
            )

        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        order_item = serializer.validated_data["order_item"]

        if order_item.order.status in [
            Order.Status.CANCELLED,
            Order.Status.DELIVERED,
            Order.Status.REFUNDED,
        ]:
            raise ValidationError(
                "Substitutions cannot be created for a completed or cancelled order."
            )

        serializer.save()

    @action(detail=True, methods=["post"])
    def respond(self, request, pk=None):
        with transaction.atomic():
            substitution = OrderSubstitution.objects.select_for_update().select_related(
                "order_item",
                "order_item__order",
            ).get(pk=pk)

            if substitution.order_item.order.customer_id != request.user.id:
                raise PermissionDenied(
                    "You cannot respond to this substitution."
                )

            if substitution.status != OrderSubstitution.Status.PENDING:
                raise ValidationError(
                    "This substitution has already been answered."
                )

            response_value = request.data.get("response")
            customer_response = request.data.get("customer_response", "")

            if response_value not in ["ACCEPTED", "REJECTED"]:
                raise ValidationError({
                    "response": "Response must be ACCEPTED or REJECTED."
                })

            substitution.status = response_value
            substitution.customer_response = customer_response
            substitution.save(update_fields=[
                "status",
                "customer_response",
            ])

        return Response(
            OrderSubstitutionSerializer(substitution).data
        )

    def update(self, request, *args, **kwargs):
        raise PermissionDenied(
            "Use the respond action to answer a substitution."
        )

    def partial_update(self, request, *args, **kwargs):
        raise PermissionDenied(
            "Use the respond action to answer a substitution."
        )

    def destroy(self, request, *args, **kwargs):
        raise PermissionDenied(
            "Substitution records cannot be deleted."
        )
