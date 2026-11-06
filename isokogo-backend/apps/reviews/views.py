
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import ProductReview
from .serializers import (
    ProductReviewSerializer,
    ProductReviewModerationSerializer,
)


class ProductReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ProductReviewSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve", "product_reviews"]:
            return [permissions.AllowAny()]

        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = ProductReview.objects.select_related(
            "customer",
            "product",
            "order_item",
            "order_item__order",
        )

        user = self.request.user

        if user.is_authenticated and user.is_staff:
            return queryset

        if user.is_authenticated:
            # Customers can see approved public reviews and their own reviews.
            return queryset.filter(
                status=ProductReview.Status.APPROVED
            ) | queryset.filter(customer=user)

        return queryset.filter(
            status=ProductReview.Status.APPROVED
        ).distinct()

    def get_serializer_class(self):
        if self.action == "moderate":
            return ProductReviewModerationSerializer

        return ProductReviewSerializer

    def perform_create(self, serializer):
        serializer.save(
            customer=self.request.user,
            status=ProductReview.Status.PENDING,
            is_verified_purchase=True,
        )

    def perform_update(self, serializer):
        review = self.get_object()

        if review.customer_id != self.request.user.id:
            raise PermissionDenied(
                "You can only update your own reviews."
            )

        if review.status not in [
            ProductReview.Status.PENDING,
            ProductReview.Status.REJECTED,
        ]:
            raise PermissionDenied(
                "Only pending or rejected reviews can be edited."
            )

        # Editing a review sends it back for moderation.
        serializer.save(status=ProductReview.Status.PENDING)

    def destroy(self, request, *args, **kwargs):
        review = self.get_object()

        if not request.user.is_staff and review.customer_id != request.user.id:
            raise PermissionDenied(
                "You can only delete your own reviews."
            )

        return super().destroy(request, *args, **kwargs)

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.AllowAny],
        url_path="product/(?P<product_id>[^/.]+)",
    )
    def product_reviews(self, request, product_id=None):
        """
        Get approved reviews for a specific product.

        GET /api/reviews/product/<product_id>/
        """

        reviews = self.get_queryset().filter(
            product_id=product_id,
            status=ProductReview.Status.APPROVED,
        )

        page = self.paginate_queryset(reviews)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(reviews, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[permissions.IsAdminUser],
        url_path="moderate",
    )
    def moderate(self, request, pk=None):
        """
        Staff moderation of a review.

        PATCH /api/reviews/<review_id>/moderate/
        """

        review = self.get_object()

        serializer = ProductReviewModerationSerializer(
            review,
            data=request.data,
            partial=True,
        )

        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data.get("status")

        allowed_statuses = [
            ProductReview.Status.APPROVED,
            ProductReview.Status.REJECTED,
            ProductReview.Status.HIDDEN,
        ]

        if new_status not in allowed_statuses:
            return Response(
                {
                    "detail": "Invalid moderation status."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save()

        return Response({
            "message": "Review moderation updated successfully.",
            "review": ProductReviewSerializer(
                review,
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
        Staff list of reviews awaiting moderation.

        GET /api/reviews/pending/
        """

        reviews = ProductReview.objects.filter(
            status=ProductReview.Status.PENDING
        ).select_related(
            "customer",
            "product",
            "order_item",
            "order_item__order",
        )

        page = self.paginate_queryset(reviews)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(reviews, many=True)
        return Response(serializer.data)
