
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone
from rest_framework import serializers

from .models import Coupon, CouponUsage, Promotion


class CouponSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)
    total_usage = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "description",
            "discount_type",
            "discount_value",
            "minimum_order_amount",
            "maximum_discount",
            "usage_limit",
            "usage_per_customer",
            "start_date",
            "expiry_date",
            "is_active",
            "is_valid",
            "total_usage",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "is_valid",
            "total_usage",
            "created_at",
            "updated_at",
        ]

    def get_total_usage(self, obj):
        return obj.usages.count()

    def validate_code(self, value):
        code = value.strip().upper()

        queryset = Coupon.objects.filter(code__iexact=code)

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                "A coupon with this code already exists."
            )

        return code

    def validate(self, attrs):
        discount_type = attrs.get(
            "discount_type",
            getattr(self.instance, "discount_type", None)
        )

        discount_value = attrs.get(
            "discount_value",
            getattr(self.instance, "discount_value", None)
        )

        start_date = attrs.get(
            "start_date",
            getattr(self.instance, "start_date", None)
        )

        expiry_date = attrs.get(
            "expiry_date",
            getattr(self.instance, "expiry_date", None)
        )

        if (
            discount_type == Coupon.DiscountType.PERCENTAGE
            and discount_value is not None
            and discount_value > Decimal("100")
        ):
            raise serializers.ValidationError({
                "discount_value": "Percentage discount cannot exceed 100."
            })

        if (
            start_date
            and expiry_date
            and expiry_date <= start_date
        ):
            raise serializers.ValidationError({
                "expiry_date": "Expiry date must be later than the start date."
            })

        return attrs


class CouponValidationInputSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    order_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01")
    )


class CouponUsageSerializer(serializers.ModelSerializer):
    coupon_code = serializers.CharField(
        source="coupon.code",
        read_only=True
    )
    customer_name = serializers.CharField(
        source="customer.get_full_name",
        read_only=True
    )
    order_number = serializers.CharField(
        source="order.order_number",
        read_only=True
    )

    class Meta:
        model = CouponUsage
        fields = [
            "id",
            "coupon",
            "coupon_code",
            "customer",
            "customer_name",
            "order",
            "order_number",
            "discount_amount",
            "used_at",
        ]
        read_only_fields = fields


class PromotionSerializer(serializers.ModelSerializer):
    is_currently_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Promotion
        fields = [
            "id",
            "name",
            "description",
            "banner_image",
            "start_date",
            "end_date",
            "status",
            "is_active",
            "is_currently_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "is_currently_active",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        start_date = attrs.get(
            "start_date",
            getattr(self.instance, "start_date", None)
        )

        end_date = attrs.get(
            "end_date",
            getattr(self.instance, "end_date", None)
        )

        if start_date and end_date and end_date <= start_date:
            raise serializers.ValidationError({
                "end_date": "End date must be later than the start date."
            })

        return attrs
