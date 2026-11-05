from rest_framework import serializers

from .models import CustomerProfile, CustomerAddress


# =====================================================
# CUSTOMER ADDRESS SERIALIZER
# =====================================================

class CustomerAddressSerializer(serializers.ModelSerializer):

    class Meta:
        model = CustomerAddress
        fields = [
            "id",
            "customer",
            "address_name",
            "recipient_name",
            "recipient_phone_number",
            "province",
            "district",
            "sector",
            "cell",
            "village",
            "street_address",
            "delivery_instructions",
            "latitude",
            "longitude",
            "is_default",
            "is_active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "customer",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        latitude = attrs.get(
            "latitude",
            getattr(self.instance, "latitude", None)
        )

        longitude = attrs.get(
            "longitude",
            getattr(self.instance, "longitude", None)
        )

        is_active = attrs.get(
            "is_active",
            getattr(self.instance, "is_active", True)
        )

        is_default = attrs.get(
            "is_default",
            getattr(self.instance, "is_default", False)
        )

        if latitude is not None and not -90 <= latitude <= 90:
            raise serializers.ValidationError({
                "latitude": "Latitude must be between -90 and 90."
            })

        if longitude is not None and not -180 <= longitude <= 180:
            raise serializers.ValidationError({
                "longitude": "Longitude must be between -180 and 180."
            })

        if is_default and not is_active:
            raise serializers.ValidationError({
                "is_default": "An inactive address cannot be the default address."
            })

        return attrs


# =====================================================
# CUSTOMER PROFILE SERIALIZER
# =====================================================

class CustomerProfileSerializer(serializers.ModelSerializer):

    addresses = CustomerAddressSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "user",
            "profile_image",
            "date_of_birth",
            "preferred_language",
            "addresses",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "user",
            "addresses",
            "created_at",
            "updated_at",
        ]