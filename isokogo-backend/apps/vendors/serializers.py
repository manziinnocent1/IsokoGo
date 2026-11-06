
from rest_framework import serializers

from .models import Vendor, VendorDocument


class VendorSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    owner_email = serializers.EmailField(
        source="owner.email",
        read_only=True
    )

    documents_count = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = [
            "id",
            "owner",
            "owner_name",
            "owner_email",
            "business_name",
            "business_description",
            "contact_phone",
            "contact_email",
            "business_address",
            "business_logo",
            "business_registration_number",
            "status",
            "rejection_reason",
            "approved_at",
            "documents_count",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "owner",
            "owner_name",
            "owner_email",
            "status",
            "rejection_reason",
            "approved_at",
            "documents_count",
            "created_at",
            "updated_at",
        ]

    def get_owner_name(self, obj):
        return (
            obj.owner.get_full_name()
            or obj.owner.get_username()
        )

    def get_documents_count(self, obj):
        return obj.documents.count()

    def validate_business_registration_number(self, value):
        value = value.strip()

        queryset = Vendor.objects.filter(
            business_registration_number__iexact=value
        )

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                "This business registration number is already registered."
            )

        return value


class VendorModerationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            Vendor.Status.APPROVED,
            Vendor.Status.REJECTED,
            Vendor.Status.SUSPENDED,
        ]
    )

    rejection_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True
    )

    def validate(self, attrs):
        new_status = attrs["status"]
        reason = attrs.get("rejection_reason")

        if new_status in [
            Vendor.Status.REJECTED,
            Vendor.Status.SUSPENDED,
        ] and not reason:
            raise serializers.ValidationError({
                "rejection_reason": (
                    "A reason is required when rejecting or suspending a vendor."
                )
            })

        return attrs


class VendorDocumentSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(
        source="vendor.business_name",
        read_only=True
    )

    class Meta:
        model = VendorDocument
        fields = [
            "id",
            "vendor",
            "vendor_name",
            "document_type",
            "document_file",
            "verification_status",
            "rejection_reason",
            "verified_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "vendor",
            "vendor_name",
            "verification_status",
            "rejection_reason",
            "verified_at",
            "created_at",
            "updated_at",
        ]


class VendorDocumentModerationSerializer(serializers.Serializer):
    verification_status = serializers.ChoiceField(
        choices=[
            VendorDocument.VerificationStatus.APPROVED,
            VendorDocument.VerificationStatus.REJECTED,
        ]
    )

    rejection_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True
    )

    def validate(self, attrs):
        if (
            attrs["verification_status"]
            == VendorDocument.VerificationStatus.REJECTED
            and not attrs.get("rejection_reason")
        ):
            raise serializers.ValidationError({
                "rejection_reason": (
                    "A rejection reason is required."
                )
            })

        return attrs
