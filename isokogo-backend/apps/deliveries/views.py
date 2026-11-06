from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied

from .models import (
    DeliveryPersonnel,
    DeliveryZone,
    Delivery,
    DeliveryTracking,
)

from .serializers import (
    DeliveryPersonnelSerializer,
    DeliveryZoneSerializer,
    DeliverySerializer,
    DeliveryTrackingSerializer,
)


# =====================================================
# DELIVERY PERSONNEL VIEWSET
# =====================================================

class DeliveryPersonnelViewSet(viewsets.ReadOnlyModelViewSet):

    serializer_class = DeliveryPersonnelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = DeliveryPersonnel.objects.select_related("user")

        if self.request.user.is_staff:
            return queryset.order_by("-id")

        return queryset.filter(
            user=self.request.user
        )

    @action(
        detail=True,
        methods=["patch"],
        url_path="availability"
    )
    def availability(self, request, pk=None):

        personnel = self.get_object()

        if not request.user.is_staff and personnel.user_id != request.user.id:
            raise PermissionDenied(
                "You cannot update another courier's availability."
            )

        if not personnel.is_verified:
            raise ValidationError(
                "Your delivery personnel account has not been verified."
            )

        new_status = request.data.get("availability_status")

        if new_status not in DeliveryPersonnel.AvailabilityStatus.values:
            raise ValidationError({
                "availability_status": "Invalid availability status."
            })

        if new_status == DeliveryPersonnel.AvailabilityStatus.AVAILABLE:

            has_active_delivery = Delivery.objects.filter(
                delivery_personnel=personnel,
                status__in=[
                    Delivery.Status.ASSIGNED,
                    Delivery.Status.PICKED_UP,
                    Delivery.Status.IN_TRANSIT,
                ]
            ).exists()

            if has_active_delivery:
                raise ValidationError(
                    "You cannot become available while handling an active delivery."
                )

        if (
            new_status == DeliveryPersonnel.AvailabilityStatus.OFFLINE
            and Delivery.objects.filter(
                delivery_personnel=personnel,
                status__in=[
                    Delivery.Status.ASSIGNED,
                    Delivery.Status.PICKED_UP,
                    Delivery.Status.IN_TRANSIT,
                ]
            ).exists()
        ):
            raise ValidationError(
                "Complete or reassign your active delivery before going offline."
            )

        personnel.availability_status = new_status
        personnel.save(update_fields=["availability_status"])

        return Response(
            self.get_serializer(personnel).data,
            status=status.HTTP_200_OK
        )


# =====================================================
# DELIVERY ZONE VIEWSET
# =====================================================

class DeliveryZoneViewSet(viewsets.ModelViewSet):

    serializer_class = DeliveryZoneSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = DeliveryZone.objects.all()

        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)

        province = self.request.query_params.get("province")
        district = self.request.query_params.get("district")

        if province:
            queryset = queryset.filter(
                province__icontains=province
            )

        if district:
            queryset = queryset.filter(
                district__icontains=district
            )

        return queryset.order_by("province", "district", "name")

    def check_permissions(self, request):
        super().check_permissions(request)

        if request.method not in ["GET", "HEAD", "OPTIONS"]:
            if not request.user.is_staff:
                raise PermissionDenied(
                    "Only administrators can manage delivery zones."
                )


# =====================================================
# DELIVERY VIEWSET
# =====================================================

class DeliveryViewSet(viewsets.ModelViewSet):

    serializer_class = DeliverySerializer
    permission_classes = [IsAuthenticated]
    http_method_names = [
        "get",
        "post",
        "patch",
        "head",
        "options",
    ]

    def get_queryset(self):
        queryset = Delivery.objects.select_related(
            "order",
            "delivery_personnel",
            "delivery_personnel__user",
            "delivery_zone",
        ).prefetch_related(
            "tracking_events"
        )

        if self.request.user.is_staff:
            return queryset

        return queryset.filter(
            delivery_personnel__user=self.request.user
        )

    def perform_create(self, serializer):

        if not self.request.user.is_staff:
            raise PermissionDenied(
                "Only administrators can create deliveries."
            )

        serializer.save()

    def update(self, request, *args, **kwargs):
        raise PermissionDenied(
            "Use the dedicated delivery actions to update delivery information."
        )

    def partial_update(self, request, *args, **kwargs):
        raise PermissionDenied(
            "Use the dedicated delivery actions to update delivery information."
        )

    # -------------------------------------------------
    # ASSIGN DELIVERY PERSONNEL
    # -------------------------------------------------

    @action(
        detail=True,
        methods=["post"],
        url_path="assign"
    )
    def assign(self, request, pk=None):

        if not request.user.is_staff:
            raise PermissionDenied(
                "Only administrators can assign delivery personnel."
            )

        delivery = self.get_object()

        if delivery.status != Delivery.Status.PENDING_ASSIGNMENT:
            raise ValidationError(
                "Only pending deliveries can be assigned."
            )

        personnel_id = request.data.get("delivery_personnel")

        if not personnel_id:
            raise ValidationError({
                "delivery_personnel": "Delivery personnel ID is required."
            })

        with transaction.atomic():

            delivery = Delivery.objects.select_for_update().get(
                pk=delivery.pk
            )

            personnel = get_object_or_404(
                DeliveryPersonnel.objects.select_for_update(),
                pk=personnel_id
            )

            if not personnel.is_verified:
                raise ValidationError(
                    "This delivery personnel has not been verified."
                )

            if (
                personnel.availability_status
                != DeliveryPersonnel.AvailabilityStatus.AVAILABLE
            ):
                raise ValidationError(
                    "This delivery personnel is not available."
                )

            # Ensure the courier does not have another active delivery
            active_delivery = Delivery.objects.filter(
                delivery_personnel=personnel,
                status__in=[
                    Delivery.Status.ASSIGNED,
                    Delivery.Status.PICKED_UP,
                    Delivery.Status.IN_TRANSIT,
                ]
            ).exists()

            if active_delivery:
                raise ValidationError(
                    "This courier already has an active delivery."
                )

            delivery.delivery_personnel = personnel
            delivery.status = Delivery.Status.ASSIGNED
            delivery.assigned_at = timezone.now()

            delivery.save(
                update_fields=[
                    "delivery_personnel",
                    "status",
                    "assigned_at",
                    "updated_at",
                ]
            )

            personnel.availability_status = (
                DeliveryPersonnel.AvailabilityStatus.BUSY
            )

            personnel.save(
                update_fields=["availability_status"]
            )

        return Response(
            self.get_serializer(delivery).data,
            status=status.HTTP_200_OK
        )

    # -------------------------------------------------
    # UPDATE DELIVERY STATUS
    # -------------------------------------------------

    @action(
        detail=True,
        methods=["post"],
        url_path="update-status"
    )
    def update_status(self, request, pk=None):

        delivery = self.get_object()

        if not request.user.is_staff:
            if (
                delivery.delivery_personnel is None
                or delivery.delivery_personnel.user_id != request.user.id
            ):
                raise PermissionDenied(
                    "You cannot update another courier's delivery."
                )

        new_status = request.data.get("status")

        # Define valid delivery status transitions
        transitions = {
            Delivery.Status.ASSIGNED: [
                Delivery.Status.PICKED_UP,
                Delivery.Status.FAILED,
            ],
            Delivery.Status.PICKED_UP: [
                Delivery.Status.IN_TRANSIT,
                Delivery.Status.FAILED,
            ],
            Delivery.Status.IN_TRANSIT: [
                Delivery.Status.DELIVERED,
                Delivery.Status.FAILED,
            ],
        }

        allowed_statuses = transitions.get(delivery.status, [])

        if new_status not in allowed_statuses:
            raise ValidationError({
                "status": (
                    f"Cannot change delivery status from "
                    f"{delivery.status} to {new_status}."
                )
            })

        with transaction.atomic():

            delivery = Delivery.objects.select_for_update().get(
                pk=delivery.pk
            )

            now = timezone.now()

            if new_status == Delivery.Status.PICKED_UP:
                delivery.picked_up_at = now

            if new_status == Delivery.Status.DELIVERED:
                delivery.delivered_at = now

            delivery.status = new_status

            delivery.save(
                update_fields=[
                    "status",
                    "picked_up_at",
                    "delivered_at",
                    "updated_at",
                ]
            )

            # Make the courier available after completion or failure
            if new_status in [
                Delivery.Status.DELIVERED,
                Delivery.Status.FAILED,
            ]:
                if delivery.delivery_personnel:
                    DeliveryPersonnel.objects.filter(
                        pk=delivery.delivery_personnel_id
                    ).update(
                        availability_status=(
                            DeliveryPersonnel.AvailabilityStatus.AVAILABLE
                        )
                    )

        return Response(
            self.get_serializer(delivery).data,
            status=status.HTTP_200_OK
        )

    # -------------------------------------------------
    # UPLOAD PROOF OF DELIVERY
    # -------------------------------------------------

    @action(
        detail=True,
        methods=["post"],
        url_path="proof-of-delivery",
        parser_classes=[MultiPartParser, FormParser],
    )
    def proof_of_delivery(self, request, pk=None):

        delivery = self.get_object()

        if not request.user.is_staff:
            if (
                delivery.delivery_personnel is None
                or delivery.delivery_personnel.user_id != request.user.id
            ):
                raise PermissionDenied(
                    "You cannot upload proof for another courier's delivery."
                )

        if delivery.status != Delivery.Status.IN_TRANSIT:
            raise ValidationError(
                "Proof of delivery can only be uploaded while the delivery is in transit."
            )

        proof = request.FILES.get("proof_of_delivery")

        if not proof:
            raise ValidationError({
                "proof_of_delivery": "A proof-of-delivery image is required."
            })

        delivery.proof_of_delivery = proof

        delivery.save(
            update_fields=[
                "proof_of_delivery",
                "updated_at",
            ]
        )

        return Response(
            self.get_serializer(delivery).data,
            status=status.HTTP_200_OK
        )


# =====================================================
# DELIVERY TRACKING VIEWSET
# =====================================================

class DeliveryTrackingViewSet(viewsets.ModelViewSet):

    serializer_class = DeliveryTrackingSerializer
    permission_classes = [IsAuthenticated]

    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    def get_queryset(self):

        queryset = DeliveryTracking.objects.select_related(
            "delivery",
            "delivery__delivery_personnel",
            "delivery__delivery_personnel__user",
        )

        if self.request.user.is_staff:
            return queryset

        return queryset.filter(
            delivery__delivery_personnel__user=self.request.user
        )

    def perform_create(self, serializer):

        delivery = serializer.validated_data["delivery"]

        if not self.request.user.is_staff:

            if (
                delivery.delivery_personnel is None
                or delivery.delivery_personnel.user_id != self.request.user.id
            ):
                raise PermissionDenied(
                    "You can only submit tracking for your assigned deliveries."
                )

        if delivery.status not in [
            Delivery.Status.PICKED_UP,
            Delivery.Status.IN_TRANSIT,
        ]:
            raise ValidationError(
                "Tracking can only be submitted after an order has been picked up."
            )

        serializer.save()