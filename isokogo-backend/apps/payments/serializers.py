
from decimal import Decimal

from django.db import transaction
from django.utils.crypto import get_random_string

from rest_framework import serializers

from .models import Payment, PaymentTransaction
from apps.orders.models import Order


class PaymentTransactionSummarySerializer(serializers.ModelSerializer):
    """
    Safe transaction information for payment details.
    Does not expose raw gateway request/response payloads.
    """

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "provider_transaction_id",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """
    Full transaction record for authorized staff.
    """

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "payment",
            "provider_transaction_id",
            "request_payload",
            "response_payload",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(
        source="order.order_number",
        read_only=True,
    )
    customer_name = serializers.SerializerMethodField()
    transactions = PaymentTransactionSummarySerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "order",
            "order_number",
            "customer",
            "customer_name",
            "payment_reference",
            "provider",
            "payment_method",
            "amount",
            "currency",
            "status",
            "transaction_id",
            "paid_at",
            "transactions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "customer",
            "payment_reference",
            "amount",
            "status",
            "transaction_id",
            "paid_at",
            "transactions",
            "created_at",
            "updated_at",
        ]

    def get_customer_name(self, obj):
        return (
            obj.customer.get_full_name()
            or obj.customer.get_username()
        )

    def validate(self, attrs):
        request = self.context.get("request")
        order = attrs.get("order")

        if not order:
            return attrs

        if request and not request.user.is_staff:
            if order.customer_id != request.user.id:
                raise serializers.ValidationError({
                    "order": "You can only make payments for your own orders."
                })

        if order.status in [
            Order.Status.CANCELLED,
            Order.Status.REFUNDED,
        ]:
            raise serializers.ValidationError({
                "order": "Payments cannot be initiated for cancelled or refunded orders."
            })

        if order.total_amount <= Decimal("0.00"):
            raise serializers.ValidationError({
                "order": "This order does not have an outstanding payable amount."
            })

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        order = validated_data["order"]

        with transaction.atomic():
            # Lock the order to avoid concurrent payment initiation
            # calculating the outstanding amount from stale payment data.
            order = Order.objects.select_for_update().get(pk=order.pk)

            if order.status in [
                Order.Status.CANCELLED,
                Order.Status.REFUNDED,
            ]:
                raise serializers.ValidationError({
                    "order": "Payments cannot be initiated for this order."
                })

            successful_payments = Payment.objects.filter(
                order=order,
                status=Payment.Status.SUCCESSFUL,
            ).aggregate(
                total=__import__("django.db.models", fromlist=["Sum"]).Sum("amount")
            )["total"] or Decimal("0.00")

            outstanding = order.total_amount - successful_payments

            if outstanding <= Decimal("0.00"):
                raise serializers.ValidationError({
                    "order": "This order has already been fully paid."
                })

            payment = Payment.objects.create(
                customer=request.user,
                payment_reference=f"PAY-{get_random_string(16).upper()}",
                amount=outstanding,
                **validated_data,
            )

            PaymentTransaction.objects.create(
                payment=payment,
                status=PaymentTransaction.Status.INITIATED,
                request_payload={
                    "provider": payment.provider,
                    "payment_method": payment.payment_method,
                    "amount": str(payment.amount),
                    "currency": payment.currency,
                },
            )

        return payment
