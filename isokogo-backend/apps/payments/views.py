
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Payment, PaymentTransaction
from .serializers import (
    PaymentSerializer,
    PaymentTransactionSerializer,
)

from apps.orders.models import Order


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    queryset = Payment.objects.select_related(
        "order",
        "customer",
    ).prefetch_related(
        "transactions",
    ).all()

    def get_queryset(self):
        queryset = super().get_queryset()

        # Customers can only access their own payments.
        if not self.request.user.is_staff:
            queryset = queryset.filter(
                customer=self.request.user
            )

        payment_status = self.request.query_params.get("status")
        provider = self.request.query_params.get("provider")
        order_id = self.request.query_params.get("order")
        payment_method = self.request.query_params.get("payment_method")

        if payment_status:
            queryset = queryset.filter(status=payment_status)

        if provider:
            queryset = queryset.filter(provider=provider)

        if order_id:
            queryset = queryset.filter(order_id=order_id)

        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)

        return queryset

    def perform_update(self, serializer):
        raise PermissionDenied(
            "Payments cannot be edited directly. Use the payment actions."
        )

    def destroy(self, request, *args, **kwargs):
        raise PermissionDenied(
            "Payment records cannot be deleted."
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """
        A customer may cancel their own pending payment.
        Staff may also cancel payments.
        """
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=pk)

            if (
                not request.user.is_staff
                and payment.customer_id != request.user.id
            ):
                raise PermissionDenied(
                    "You cannot cancel another customer's payment."
                )

            if payment.status not in [
                Payment.Status.PENDING,
                Payment.Status.PROCESSING,
            ]:
                raise ValidationError(
                    "Only pending or processing payments can be cancelled."
                )

            payment.status = Payment.Status.CANCELLED
            payment.save(update_fields=[
                "status",
                "updated_at",
            ])

        return Response({
            "message": "Payment cancelled successfully.",
            "payment": PaymentSerializer(
                payment,
                context=self.get_serializer_context(),
            ).data,
        })

    @action(detail=True, methods=["post"])
    def update_status(self, request, pk=None):
        """
        Staff-only administrative status update.

        In a real payment integration, successful payment confirmation
        should come from a verified provider callback, not a customer.
        """
        if not request.user.is_staff:
            raise PermissionDenied(
                "Only authorized staff can update payment status."
            )

        new_status = request.data.get("status")
        transaction_id = request.data.get("transaction_id")

        allowed_transitions = {
            Payment.Status.PENDING: [
                Payment.Status.PROCESSING,
                Payment.Status.SUCCESSFUL,
                Payment.Status.FAILED,
                Payment.Status.CANCELLED,
            ],
            Payment.Status.PROCESSING: [
                Payment.Status.SUCCESSFUL,
                Payment.Status.FAILED,
                Payment.Status.CANCELLED,
            ],
            Payment.Status.SUCCESSFUL: [
                Payment.Status.REFUNDED,
            ],
            Payment.Status.FAILED: [],
            Payment.Status.CANCELLED: [],
            Payment.Status.REFUNDED: [],
        }

        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=pk)

            if new_status not in Payment.Status.values:
                raise ValidationError({
                    "status": "Invalid payment status."
                })

            if new_status not in allowed_transitions[payment.status]:
                raise ValidationError({
                    "status": (
                        f"Cannot change payment from {payment.status} "
                        f"to {new_status}."
                    )
                })

            if new_status == Payment.Status.SUCCESSFUL:
                if not transaction_id:
                    raise ValidationError({
                        "transaction_id": (
                            "A provider transaction ID is required "
                            "for successful payments."
                        )
                    })

                other_successful = Payment.objects.filter(
                    order=payment.order,
                    status=Payment.Status.SUCCESSFUL,
                ).exclude(
                    pk=payment.pk,
                ).aggregate(
                    total=Sum("amount")
                )["total"] or 0

                if other_successful + payment.amount > payment.order.total_amount:
                    raise ValidationError(
                        "This payment would cause the order to be overpaid."
                    )

                payment.paid_at = timezone.now()
                payment.transaction_id = transaction_id

            payment.status = new_status
            payment.save(update_fields=[
                "status",
                "transaction_id",
                "paid_at",
                "updated_at",
            ])

            # Record the administrative status change.
            transaction_status = {
                Payment.Status.PENDING: PaymentTransaction.Status.PENDING,
                Payment.Status.PROCESSING: PaymentTransaction.Status.PENDING,
                Payment.Status.SUCCESSFUL: PaymentTransaction.Status.SUCCESSFUL,
                Payment.Status.FAILED: PaymentTransaction.Status.FAILED,
                Payment.Status.CANCELLED: PaymentTransaction.Status.FAILED,
                Payment.Status.REFUNDED: PaymentTransaction.Status.REVERSED,
            }[new_status]

            PaymentTransaction.objects.create(
                payment=payment,
                provider_transaction_id=transaction_id,
                status=transaction_status,
                response_payload={
                    "updated_by": request.user.get_username(),
                    "payment_status": new_status,
                    "note": request.data.get("note", ""),
                },
            )

        return Response({
            "message": "Payment status updated successfully.",
            "payment": PaymentSerializer(
                payment,
                context=self.get_serializer_context(),
            ).data,
        })


class PaymentTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Transaction history is restricted to staff.
    Raw provider payloads should not be exposed to customers.
    """

    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    queryset = PaymentTransaction.objects.select_related(
        "payment",
        "payment__order",
        "payment__customer",
    ).all()

    def get_queryset(self):
        if not self.request.user.is_staff:
            raise PermissionDenied(
                "You are not authorized to access payment transaction records."
            )

        queryset = super().get_queryset()

        payment_id = self.request.query_params.get("payment")
        transaction_status = self.request.query_params.get("status")

        if payment_id:
            queryset = queryset.filter(payment_id=payment_id)

        if transaction_status:
            queryset = queryset.filter(status=transaction_status)

        return queryset
