
from django.db import transaction
from django.utils import timezone

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import (
    MultiPartParser,
    FormParser,
    JSONParser,
)
from rest_framework.response import Response

from .models import Vendor, VendorDocument
from .serializers import (
    VendorSerializer,
    VendorModerationSerializer,
    VendorDocumentSerializer,
    VendorDocumentModerationSerializer,
)


class VendorViewSet(viewsets.ModelViewSet):
    serializer_class = VendorSerializer

    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "head",
        "options",
    ]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]

        if self.action == "moderate":
            return [permissions.IsAdminUser()]

        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = Vendor.objects.select_related(
            "owner"
        ).prefetch_related(
            "documents"
        )

        user = self.request.user

        # Administrators can access all vendor applications.
        if user.is_authenticated and user.is_staff:
            return queryset

        # Public users can only see approved vendors.
        public_queryset = queryset.filter(
            status=Vendor.Status.APPROVED
        )

        # Vendors can also see their own applications.
        if user.is_authenticated:
            return (
                public_queryset
                | queryset.filter(owner=user)
            ).distinct()

        return public_queryset

    def perform_create(self, serializer):
        user = self.request.user

        if Vendor.objects.filter(owner=user).exists():
            raise ValidationError({
                "detail": "You already have a vendor application."
            })

        serializer.save(
            owner=user,
            status=Vendor.Status.PENDING,
        )

    def destroy(self, request, *args, **kwargs):
        raise PermissionDenied(
            "Vendor profiles cannot be deleted through this API. "
            "Contact an administrator if your account needs to be removed."
        )

    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[permissions.IsAdminUser],
        url_path="moderate",
    )
    def moderate(self, request, pk=None):
        """
        Approve, reject, or suspend a vendor.

        PATCH /api/vendors/vendors/{id}/moderate/
        """

        serializer = VendorModerationSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        rejection_reason = serializer.validated_data.get(
            "rejection_reason"
        )

        with transaction.atomic():
            vendor = Vendor.objects.select_for_update().get(
                pk=pk
            )

            vendor.status = new_status

            if new_status == Vendor.Status.APPROVED:
                vendor.approved_at = timezone.now()
                vendor.rejection_reason = None

            elif new_status in [
                Vendor.Status.REJECTED,
                Vendor.Status.SUSPENDED,
            ]:
                vendor.rejection_reason = rejection_reason

            vendor.save(
                update_fields=[
                    "status",
                    "approved_at",
                    "rejection_reason",
                    "updated_at",
                ]
            )

        return Response({
            "message": "Vendor status updated successfully.",
            "vendor": VendorSerializer(
                vendor,
                context={"request": request},
            ).data,
        })

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.IsAdminUser],
        url_path="statistics",
    )
    def statistics(self, request):
        """
        Vendor registration statistics.

        GET /api/vendors/vendors/statistics/
        """

        queryset = Vendor.objects.all()

        return Response({
            "total_vendors": queryset.count(),
            "pending_vendors": queryset.filter(
                status=Vendor.Status.PENDING
            ).count(),
            "approved_vendors": queryset.filter(
                status=Vendor.Status.APPROVED
            ).count(),
            "rejected_vendors": queryset.filter(
                status=Vendor.Status.REJECTED
            ).count(),
            "suspended_vendors": queryset.filter(
                status=Vendor.Status.SUSPENDED
            ).count(),
        })


class VendorDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = VendorDocumentSerializer

    parser_classes = [
        MultiPartParser,
        FormParser,
        JSONParser,
    ]

    def get_permissions(self):
        if self.action == "verify":
            return [permissions.IsAdminUser()]

        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = VendorDocument.objects.select_related(
            "vendor",
            "vendor__owner",
        )

        user = self.request.user

        if user.is_staff:
            return queryset

        return queryset.filter(
            vendor__owner=user
        )

    def get_serializer_class(self):
        if self.action == "verify":
            return VendorDocumentModerationSerializer

        return VendorDocumentSerializer

    def perform_create(self, serializer):
        user = self.request.user

        try:
            vendor = Vendor.objects.get(owner=user)
        except Vendor.DoesNotExist:
            raise ValidationError({
                "detail": (
                    "You must register as a vendor before uploading documents."
                )
            })

        if vendor.status == Vendor.Status.SUSPENDED:
            raise PermissionDenied(
                "Suspended vendors cannot upload documents."
            )

        serializer.save(vendor=vendor)

    def perform_update(self, serializer):
        document = self.get_object()

        if not self.request.user.is_staff:
            if (
                document.verification_status
                == VendorDocument.VerificationStatus.APPROVED
            ):
                raise PermissionDenied(
                    "Approved documents cannot be modified. "
                    "Upload a new document if an updated certificate is required."
                )

        serializer.save()

    def destroy(self, request, *args, **kwargs):
        document = self.get_object()

        if not request.user.is_staff:
            if (
                document.verification_status
                == VendorDocument.VerificationStatus.APPROVED
            ):
                raise PermissionDenied(
                    "Approved documents cannot be deleted."
                )

        return super().destroy(request, *args, **kwargs)

    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[permissions.IsAdminUser],
        url_path="verify",
    )
    def verify(self, request, pk=None):
        """
        Approve or reject a vendor document.

        PATCH /api/vendors/documents/{id}/verify/
        """

        serializer = VendorDocumentModerationSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data[
            "verification_status"
        ]

        rejection_reason = serializer.validated_data.get(
            "rejection_reason"
        )

        with transaction.atomic():
            document = VendorDocument.objects.select_for_update().get(
                pk=pk
            )

            document.verification_status = new_status

            if (
                new_status
                == VendorDocument.VerificationStatus.APPROVED
            ):
                document.verified_at = timezone.now()
                document.rejection_reason = None

            else:
                document.verified_at = None
                document.rejection_reason = rejection_reason

            document.save(
                update_fields=[
                    "verification_status",
                    "verified_at",
                    "rejection_reason",
                    "updated_at",
                ]
            )

        return Response({
            "message": "Vendor document verification updated successfully.",
            "document": VendorDocumentSerializer(
                document,
                context={"request": request},
            ).data,
        })

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.IsAdminUser],
        url_path="pending",
    )
    def pending(self, request):
        """
        List documents awaiting verification.

        GET /api/vendors/documents/pending/
        """

        documents = self.get_queryset().filter(
            verification_status=VendorDocument.VerificationStatus.PENDING
        )

        page = self.paginate_queryset(documents)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(
            documents,
            many=True
        )

        return Response(serializer.data)
