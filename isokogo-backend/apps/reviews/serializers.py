
from rest_framework import serializers

from .models import ProductReview


class ProductReviewSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    product_name = serializers.CharField(
        source="product.name",
        read_only=True
    )
    order_number = serializers.CharField(
        source="order_item.order.order_number",
        read_only=True
    )

    class Meta:
        model = ProductReview
        fields = [
            "id",
            "customer",
            "customer_name",
            "product",
            "product_name",
            "order_item",
            "order_number",
            "rating",
            "comment",
            "status",
            "is_verified_purchase",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "customer",
            "customer_name",
            "product_name",
            "order_number",
            "status",
            "is_verified_purchase",
            "created_at",
            "updated_at",
        ]

    def get_customer_name(self, obj):
        full_name = obj.customer.get_full_name()
        return full_name or obj.customer.get_username()

    def validate(self, attrs):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(
                "Authentication is required to submit a review."
            )

        product = attrs.get(
            "product",
            getattr(self.instance, "product", None)
        )

        order_item = attrs.get(
            "order_item",
            getattr(self.instance, "order_item", None)
        )

        if product and order_item:
            if order_item.product_id != product.id:
                raise serializers.ValidationError({
                    "order_item": "This order item does not belong to the selected product."
                })

            if order_item.order.customer_id != request.user.id:
                raise serializers.ValidationError({
                    "order_item": "You can only review products from your own orders."
                })

            if order_item.order.status not in [
                "delivered",
            ]:
                raise serializers.ValidationError({
                    "order_item": "You can only review products from delivered orders."
                })

            existing_reviews = ProductReview.objects.filter(
                customer=request.user,
                product=product,
                order_item=order_item,
            )

            if self.instance:
                existing_reviews = existing_reviews.exclude(
                    pk=self.instance.pk
                )

            if existing_reviews.exists():
                raise serializers.ValidationError(
                    "You have already reviewed this product from this order item."
                )

        return attrs


class ProductReviewModerationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductReview
        fields = [
            "id",
            "status",
        ]

        read_only_fields = ["id"]
