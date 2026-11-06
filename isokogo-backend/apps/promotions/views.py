
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
    BasePermission,
)
from rest_framework.response import Response

from .models import Coupon, CouponUsage, Promotion
from .serializers import (
    CouponSerializer,
    CouponUsageSerializer,
    CouponValidationInputSerializer,
    PromotionSerializer,
)


class StaffWritePermission(BasePermission):
    """
    Public read access.
    Staff-only create, update and delete access.
    """

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True

        if getattr(view, "action", None) == "validate":
            return request.user and request.user.is_authenticated

        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


class CouponViewSet(viewsets.ModelViewSet):
    serializer_class = CouponSerializer
    permission_classes = [StaffWritePermission]

    def get_queryset(self):
        queryset = Coupon.objects.all()
        user = self.request.user

        # Staff can manage all coupons.
        if user.is_authenticated and user.is_staff:
            return queryset

        # Customers can only view currently valid coupons.
        now = timezone.now()

        queryset = queryset.filter(
            is_active=True,
            start_date__lte=now,
            expiry_date__gte=now,
        )

        return queryset

    def get_serializer_class(self):
        if getattr(self, "action", None) == "validate":
            return CouponValidationInputSerializer

        return CouponSerializer

    def perform_destroy(self, instance):
        if instance.usages.exists():
            raise PermissionDenied(
                "This coupon has usage records and cannot be deleted. "
                "Deactivate it instead."
            )

        instance.delete()

    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAuthenticated],
        url_path="validate",
    )
    def validate(self, request):
        """
        Validate a coupon before checkout.

        POST /api/promotions/coupons/validate/
        """

        serializer = CouponValidationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data["code"].strip().upper()
        order_amount = serializer.validated_data["order_amount"]

        now = timezone.now()

        coupon = Coupon.objects.filter(
            code__iexact=code
        ).first()

        if not coupon:
            return Response(
                {
                    "valid": False,
                    "message": "Coupon does not exist.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not coupon.is_active:
            return Response({
                "valid": False,
                "message": "This coupon is inactive.",
            })

        if now < coupon.start_date:
            return Response({
                "valid": False,
                "message": "This coupon is not active yet.",
            })

        if now > coupon.expiry_date:
            return Response({
                "valid": False,
                "message": "This coupon has expired.",
            })

        if order_amount < coupon.minimum_order_amount:
            return Response({
                "valid": False,
                "message": (
                    f"Minimum order amount is "
                    f"{coupon.minimum_order_amount}."
                ),
            })

        # Check the overall coupon usage limit.
        total_usage = CouponUsage.objects.filter(
            coupon=coupon
        ).count()

        if (
            coupon.usage_limit is not None
            and total_usage >= coupon.usage_limit
        ):
            return Response({
                "valid": False,
                "message": "This coupon has reached its usage limit.",
            })

        # Check the customer's usage limit.
        customer_usage = CouponUsage.objects.filter(
            coupon=coupon,
            customer=request.user,
        ).count()

        if customer_usage >= coupon.usage_per_customer:
            return Response({
                "valid": False,
                "message": "You have already used this coupon the maximum number of times.",
            })

        # Calculate the discount.
        discount_amount = Decimal("0.00")
        free_delivery = False

        if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
            discount_amount = (
                order_amount * coupon.discount_value / Decimal("100")
            )

            if coupon.maximum_discount is not None:
                discount_amount = min(
                    discount_amount,
                    coupon.maximum_discount
                )

        elif coupon.discount_type == Coupon.DiscountType.FIXED:
            discount_amount = min(
                coupon.discount_value,
                order_amount
            )

        elif coupon.discount_type == Coupon.DiscountType.FREE_DELIVERY:
            free_delivery = True

        discount_amount = min(discount_amount, order_amount)
        discount_amount = discount_amount.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

        return Response({
            "valid": True,
            "message": "Coupon is valid.",
            "coupon": {
                "id": str(coupon.id),
                "code": coupon.code,
                "description": coupon.description,
                "discount_type": coupon.discount_type,
                "discount_value": str(coupon.discount_value),
            },
            "order_amount": str(order_amount),
            "discount_amount": str(discount_amount),
            "free_delivery": free_delivery,
            "final_subtotal": str(order_amount - discount_amount),
        })


class CouponUsageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CouponUsageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        queryset = CouponUsage.objects.select_related(
            "coupon",
            "customer",
            "order",
        )

        if user.is_staff:
            return queryset

        return queryset.filter(customer=user)


class PromotionViewSet(viewsets.ModelViewSet):
    serializer_class = PromotionSerializer
    permission_classes = [StaffWritePermission]

    def get_queryset(self):
        queryset = Promotion.objects.all()
        user = self.request.user

        # Staff can see and manage all promotions.
        if user.is_authenticated and user.is_staff:
            return queryset

        # Public users see only currently active promotions.
        now = timezone.now()

        return queryset.filter(
            is_active=True,
            status=Promotion.Status.ACTIVE,
            start_date__lte=now,
            end_date__gte=now,
        )

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[AllowAny],
        url_path="current",
    )
    def current(self, request):
        """
        Return all promotions currently active.

        GET /api/promotions/promotions/current/
        """

        now = timezone.now()

        promotions = Promotion.objects.filter(
            is_active=True,
            status=Promotion.Status.ACTIVE,
            start_date__lte=now,
            end_date__gte=now,
        ).order_by("-created_at")

        serializer = self.get_serializer(
            promotions,
            many=True,
            context={"request": request},
        )

        return Response(serializer.data)
