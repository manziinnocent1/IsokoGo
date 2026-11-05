from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from .models import CustomerProfile, CustomerAddress

from .serializers import (
    CustomerProfileSerializer,
    CustomerAddressSerializer,
)


# =====================================================
# CUSTOMER PROFILE VIEWSET
# =====================================================

class CustomerProfileViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):

    serializer_class = CustomerProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            CustomerProfile.objects
            .filter(user=self.request.user)
            .prefetch_related("addresses")
        )

    def perform_create(self, serializer):
        if CustomerProfile.objects.filter(
            user=self.request.user
        ).exists():
            raise ValidationError({
                "detail": "You already have a customer profile."
            })

        serializer.save(user=self.request.user)


# =====================================================
# CUSTOMER ADDRESS VIEWSET
# =====================================================

class CustomerAddressViewSet(viewsets.ModelViewSet):

    serializer_class = CustomerAddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            CustomerAddress.objects
            .filter(customer__user=self.request.user)
            .order_by("-created_at")
        )

    def perform_create(self, serializer):

        profile, _ = CustomerProfile.objects.get_or_create(
            user=self.request.user
        )

        with transaction.atomic():

            # Lock the customer profile while changing default addresses
            profile = CustomerProfile.objects.select_for_update().get(
                pk=profile.pk
            )

            if serializer.validated_data.get("is_default", False):

                CustomerAddress.objects.filter(
                    customer=profile,
                    is_default=True
                ).update(is_default=False)

            serializer.save(customer=profile)

    def perform_update(self, serializer):

        address = self.get_object()

        with transaction.atomic():

            profile = CustomerProfile.objects.select_for_update().get(
                pk=address.customer_id
            )

            if serializer.validated_data.get("is_default", False):

                CustomerAddress.objects.filter(
                    customer=profile,
                    is_default=True
                ).exclude(
                    pk=address.pk
                ).update(is_default=False)

            serializer.save()

    def perform_destroy(self, instance):

        with transaction.atomic():

            CustomerProfile.objects.select_for_update().get(
                pk=instance.customer_id
            )

            instance.delete()