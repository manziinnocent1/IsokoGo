from rest_framework import serializers

from .models import (
    DeliveryPersonnel,
    DeliveryZone,
    Delivery,
    DeliveryTracking,
)


# =====================================================
# DELIVERY PERSONNEL SERIALIZER
# =====================================================

class DeliveryPersonnelSerializer(serializers.ModelSerializer):

    user_name = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryPersonnel
        fields = [
            "id",
            "user",
            "user_name",
            "vehicle_type",
            "vehicle_registration",
            "availability_status",
            "is_verified",
        ]

        read_only_fields = [
            "id",
        ]

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.get_username()


# =====================================================
# DELIVERY ZONE SERIALIZER
# =====================================================

class DeliveryZoneSerializer(serializers.ModelSerializer):

    class Meta:
        model = DeliveryZone
        fields = [
            "id",
            "name",
            "province",
            "district",
            "base_delivery_fee",
            "estimated_delivery_minutes",
            "is_active",
        ]

        read_only_fields = [
            "id",
        ]

    def validate(self, attrs):
        fee = attrs.get(
            "base_delivery_fee",
            getattr(self.instance, "base_delivery_fee", None)
        )

        estimated_minutes = attrs.get(
            "estimated_delivery_minutes",
            getattr(self.instance, "estimated_delivery_minutes", None)
        )

        if fee is not None and fee < 0:
            raise serializers.ValidationError({
                "base_delivery_fee": "Delivery fee cannot be negative."
            })

        if estimated_minutes is not None and estimated_minutes <= 0:
            raise serializers.ValidationError({
                "estimated_delivery_minutes": (
                    "Estimated delivery time must be greater than zero."
                )
            })

        return attrs


# =====================================================
# DELIVERY TRACKING SERIALIZER
# =====================================================

class DeliveryTrackingSerializer(serializers.ModelSerializer):

    class Meta:
        model = DeliveryTracking
        fields = [
            "id",
            "delivery",
            "latitude",
            "longitude",
            "recorded_at",
        ]

        read_only_fields = [
            "id",
            "recorded_at",
        ]

    def validate(self, attrs):
        latitude = attrs.get("latitude")
        longitude = attrs.get("longitude")

        if latitude is not None and not -90 <= latitude <= 90:
            raise serializers.ValidationError({
                "latitude": "Latitude must be between -90 and 90."
            })

        if longitude is not None and not -180 <= longitude <= 180:
            raise serializers.ValidationError({
                "longitude": "Longitude must be between -180 and 180."
            })

        delivery = attrs.get(
            "delivery",
            getattr(self.instance, "delivery", None)
        )

        request = self.context.get("request")

        if delivery and request:
            if not request.user.is_staff:
                if delivery.delivery_personnel_id is None:
                    raise serializers.ValidationError({
                        "delivery": "This delivery has no assigned courier."
                    })

                if delivery.delivery_personnel.user_id != request.user.id:
                    raise serializers.ValidationError({
                        "delivery": "You cannot track another courier's delivery."
                    })

        return attrs


# =====================================================
# DELIVERY SERIALIZER
# =====================================================

class DeliverySerializer(serializers.ModelSerializer):

    tracking_events = DeliveryTrackingSerializer(
        many=True,
        read_only=True
    )

    delivery_personnel_name = serializers.SerializerMethodField()

    delivery_zone_name = serializers.CharField(
        source="delivery_zone.name",
        read_only=True
    )

    order_reference = serializers.CharField(
        source="order_id",
        read_only=True
    )

    class Meta:
        model = Delivery
        fields = [
            "id",
            "order",
            "order_reference",
            "delivery_personnel",
            "delivery_personnel_name",
            "delivery_zone",
            "delivery_zone_name",
            "status",
            "assigned_at",
            "picked_up_at",
            "delivered_at",
            "delivery_fee",
            "recipient_name",
            "recipient_phone",
            "proof_of_delivery",
            "delivery_notes",
            "tracking_events",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "status",
            "assigned_at",
            "picked_up_at",
            "delivered_at",
            "delivery_personnel",
            "proof_of_delivery",
            "tracking_events",
            "created_at",
            "updated_at",
        ]

    def get_delivery_personnel_name(self, obj):
        if obj.delivery_personnel:
            user = obj.delivery_personnel.user
            return user.get_full_name() or user.get_username()

        return None

    def validate_delivery_fee(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Delivery fee cannot be negative."
            )

        return value