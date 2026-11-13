
import pytest

from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductVariant
from apps.vendors.models import Vendor
from apps.orders.models import Order, OrderItem

from .models import ProductReview
from .serializers import (
    ProductReviewSerializer,
    ProductReviewModerationSerializer,
)


User = get_user_model()


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def customer(db):
    return User.objects.create_user(
        email="customer@example.com",
        password="TestPassword123!",
    )


@pytest.fixture
def another_customer(db):
    return User.objects.create_user(
        email="another@example.com",
        password="TestPassword123!",
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        email="staff@example.com",
        password="StaffPassword123!",
        is_staff=True,
    )


@pytest.fixture
def vendor(db, customer):
    return Vendor.objects.create(
        owner=customer,
        businness_name="IsokoGo Food Store",
        businness_description="Food and grocery supplier",
        contact_phone="+250788123456",
        contact_email="vendor@example.com",
        businness_address="Kigali, Rwanda",
        business_registration_number="REG-REV-001",
    )


@pytest.fixture
def category(db):
    return Category.objects.create(
        name="Food",
        slug="food",
        description="Food products",
    )


@pytest.fixture
def product(db, category, vendor):
    return Product.objects.create(
        name="Rice",
        slug="rice",
        sku="RICE-001",
        description="Premium quality rice",
        category=category,
        vendor=vendor,
        base_price=Decimal("3000.00"),
    )


@pytest.fixture
def another_product(db, category, vendor):
    return Product.objects.create(
        name="Cooking Oil",
        slug="cooking-oil",
        sku="OIL-001",
        description="Cooking oil",
        category=category,
        vendor=vendor,
        base_price=Decimal("5000.00"),
    )


@pytest.fixture
def product_variant(db, product):
    return ProductVariant.objects.create(
        product=product,
        name="5 KG",
        sku="RICE-001-5KG",
        size_value=Decimal("5.00"),
        size_unit="kg",
        selling_price=Decimal("3000.00"),
    )


@pytest.fixture
def another_product_variant(db, another_product):
    return ProductVariant.objects.create(
        product=another_product,
        name="1 Litre",
        sku="OIL-001-1L",
        size_value=Decimal("1.00"),
        size_unit="litre",
        selling_price=Decimal("5000.00"),
    )


@pytest.fixture
def delivered_order(db, customer):
    return Order.objects.create(
        order_number="ORD-REVIEW-001",
        customer=customer,
        status="delivered",
        delivery_address_snapshot={
            "address": "Kigali, Rwanda"
        },
    )


@pytest.fixture
def pending_order(db, customer):
    return Order.objects.create(
        order_number="ORD-REVIEW-002",
        customer=customer,
        status="pending",
        delivery_address_snapshot={
            "address": "Kigali, Rwanda"
        },
    )


@pytest.fixture
def another_customer_order(db, another_customer):
    return Order.objects.create(
        order_number="ORD-REVIEW-003",
        customer=another_customer,
        status="delivered",
        delivery_address_snapshot={
            "address": "Kigali, Rwanda"
        },
    )


@pytest.fixture
def delivered_order_item(
    db,
    delivered_order,
    product,
    product_variant,
):
    return OrderItem.objects.create(
        order=delivered_order,
        product=product,
        variant=product_variant,
        product_name=product.name,
        variant_name=product_variant.name,
        sku=product_variant.sku,
        quantity=Decimal("2.00"),
        unit_price=Decimal("3000.00"),
    )


@pytest.fixture
def pending_order_item(
    db,
    pending_order,
    product,
    product_variant,
):
    return OrderItem.objects.create(
        order=pending_order,
        product=product,
        variant=product_variant,
        product_name=product.name,
        variant_name=product_variant.name,
        sku=product_variant.sku,
        quantity=Decimal("1.00"),
        unit_price=Decimal("3000.00"),
    )


@pytest.fixture
def another_customer_order_item(
    db,
    another_customer_order,
    product,
    product_variant,
):
    return OrderItem.objects.create(
        order=another_customer_order,
        product=product,
        variant=product_variant,
        product_name=product.name,
        variant_name=product_variant.name,
        sku=product_variant.sku,
        quantity=Decimal("1.00"),
        unit_price=Decimal("3000.00"),
    )


@pytest.fixture
def pending_review(
    db,
    customer,
    product,
    delivered_order_item,
):
    return ProductReview.objects.create(
        customer=customer,
        product=product,
        order_item=delivered_order_item,
        rating=5,
        comment="Excellent product!",
        status=ProductReview.Status.PENDING,
        is_verified_purchase=True,
    )


@pytest.fixture
def approved_review(
    db,
    customer,
    product,
    delivered_order_item,
):
    return ProductReview.objects.create(
        customer=customer,
        product=product,
        order_item=delivered_order_item,
        rating=5,
        comment="Excellent product!",
        status=ProductReview.Status.APPROVED,
        is_verified_purchase=True,
    )


# ============================================================
# PRODUCT REVIEW MODEL TESTS
# ============================================================

@pytest.mark.django_db
class TestProductReviewModel:

    def test_create_review(self, pending_review):
        assert pending_review.rating == 5
        assert pending_review.status == ProductReview.Status.PENDING
        assert pending_review.comment == "Excellent product!"

    def test_review_has_uuid(self, pending_review):
        assert pending_review.id is not None

    def test_review_string_representation(self, pending_review):
        assert str(pending_review) == "Rice - 5/5"

    def test_default_review_status(
        self,
        db,
        customer,
        product,
        delivered_order_item,
    ):
        review = ProductReview.objects.create(
            customer=customer,
            product=product,
            order_item=delivered_order_item,
            rating=4,
        )

        assert review.status == ProductReview.Status.PENDING

    def test_default_verified_purchase(
        self,
        db,
        customer,
        product,
        delivered_order_item,
    ):
        review = ProductReview.objects.create(
            customer=customer,
            product=product,
            order_item=delivered_order_item,
            rating=4,
        )

        assert review.is_verified_purchase is True

    def test_duplicate_review_database_constraint(
        self,
        customer,
        product,
        delivered_order_item,
    ):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ProductReview.objects.create(
                    customer=customer,
                    product=product,
                    order_item=delivered_order_item,
                    rating=4,
                )

    def test_reviews_are_ordered_by_newest_first(
        self,
        pending_review,
    ):
        reviews = ProductReview.objects.all()

        assert reviews.first() == pending_review


# ============================================================
# PRODUCT REVIEW SERIALIZER TESTS
# ============================================================

@pytest.mark.django_db
class TestProductReviewSerializer:

    def test_valid_review_serializer(
        self,
        customer,
        product,
        delivered_order_item,
    ):
        request = APIClient()
        request.force_authenticate(user=customer)

        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        http_request = factory.post("/api/reviews/")
        http_request.user = customer

        serializer = ProductReviewSerializer(
            data={
                "product": str(product.id),
                "order_item": str(delivered_order_item.id),
                "rating": 5,
                "comment": "Excellent product!",
            },
            context={"request": http_request},
        )

        assert serializer.is_valid(), serializer.errors

    def test_authentication_required(
        self,
        product,
        delivered_order_item,
    ):
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        http_request = factory.post("/api/reviews/")

        serializer = ProductReviewSerializer(
            data={
                "product": str(product.id),
                "order_item": str(delivered_order_item.id),
                "rating": 5,
            },
            context={"request": http_request},
        )

        assert serializer.is_valid() is False

    def test_rating_below_one_is_invalid(
        self,
        customer,
        product,
        delivered_order_item,
    ):
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        http_request = factory.post("/api/reviews/")
        http_request.user = customer

        serializer = ProductReviewSerializer(
            data={
                "product": str(product.id),
                "order_item": str(delivered_order_item.id),
                "rating": 0,
            },
            context={"request": http_request},
        )

        assert serializer.is_valid() is False
        assert "rating" in serializer.errors

    def test_rating_above_five_is_invalid(
        self,
        customer,
        product,
        delivered_order_item,
    ):
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        http_request = factory.post("/api/reviews/")
        http_request.user = customer

        serializer = ProductReviewSerializer(
            data={
                "product": str(product.id),
                "order_item": str(delivered_order_item.id),
                "rating": 6,
            },
            context={"request": http_request},
        )

        assert serializer.is_valid() is False
        assert "rating" in serializer.errors

    def test_order_item_must_belong_to_selected_product(
        self,
        customer,
        another_product,
        delivered_order_item,
    ):
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        http_request = factory.post("/api/reviews/")
        http_request.user = customer

        serializer = ProductReviewSerializer(
            data={
                "product": str(another_product.id),
                "order_item": str(delivered_order_item.id),
                "rating": 5,
            },
            context={"request": http_request},
        )

        assert serializer.is_valid() is False
        assert "order_item" in serializer.errors

    def test_customer_cannot_review_another_customers_order(
        self,
        customer,
        product,
        another_customer_order_item,
    ):
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        http_request = factory.post("/api/reviews/")
        http_request.user = customer

        serializer = ProductReviewSerializer(
            data={
                "product": str(product.id),
                "order_item": str(another_customer_order_item.id),
                "rating": 5,
            },
            context={"request": http_request},
        )

        assert serializer.is_valid() is False
        assert "order_item" in serializer.errors

    def test_customer_can_only_review_delivered_orders(
        self,
        customer,
        product,
        pending_order_item,
    ):
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        http_request = factory.post("/api/reviews/")
        http_request.user = customer

        serializer = ProductReviewSerializer(
            data={
                "product": str(product.id),
                "order_item": str(pending_order_item.id),
                "rating": 5,
            },
            context={"request": http_request},
        )

        assert serializer.is_valid() is False
        assert "order_item" in serializer.errors

    def test_customer_cannot_review_same_order_item_twice(
        self,
        customer,
        product,
        delivered_order_item,
        pending_review,
    ):
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        http_request = factory.post("/api/reviews/")
        http_request.user = customer

        serializer = ProductReviewSerializer(
            data={
                "product": str(product.id),
                "order_item": str(delivered_order_item.id),
                "rating": 4,
            },
            context={"request": http_request},
        )

        assert serializer.is_valid() is False

    def test_customer_name_is_returned(
        self,
        pending_review,
    ):
        serializer = ProductReviewSerializer(pending_review)

        assert "customer_name" in serializer.data

    def test_product_name_is_returned(
        self,
        pending_review,
    ):
        serializer = ProductReviewSerializer(pending_review)

        assert serializer.data["product_name"] == "Rice"

    def test_order_number_is_returned(
        self,
        pending_review,
    ):
        serializer = ProductReviewSerializer(pending_review)

        assert serializer.data["order_number"] == "ORD-REVIEW-001"

    def test_moderation_serializer(self, pending_review):
        serializer = ProductReviewModerationSerializer(
            pending_review,
            data={"status": ProductReview.Status.APPROVED},
            partial=True,
        )

        assert serializer.is_valid(), serializer.errors


# ============================================================
# REVIEW API TESTS
# ============================================================

@pytest.mark.django_db
class TestProductReviewAPI:

    list_url = "/api/reviews/"

    def test_anonymous_user_can_view_reviews(
        self,
        api_client,
        approved_review,
    ):
        response = api_client.get(self.list_url)

        assert response.status_code == status.HTTP_200_OK

    def test_anonymous_user_cannot_create_review(
        self,
        api_client,
        product,
        delivered_order_item,
    ):
        response = api_client.post(
            self.list_url,
            {
                "product": str(product.id),
                "order_item": str(delivered_order_item.id),
                "rating": 5,
                "comment": "Excellent!",
            },
            format="json",
        )

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_customer_can_create_review(
        self,
        api_client,
        customer,
        product,
        delivered_order_item,
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(
            self.list_url,
            {
                "product": str(product.id),
                "order_item": str(delivered_order_item.id),
                "rating": 5,
                "comment": "Excellent product!",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        review = ProductReview.objects.get(
            customer=customer,
            order_item=delivered_order_item,
        )

        assert review.status == ProductReview.Status.PENDING
        assert review.is_verified_purchase is True

    def test_customer_cannot_submit_review_for_undelivered_order(
        self,
        api_client,
        customer,
        product,
        pending_order_item,
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(
            self.list_url,
            {
                "product": str(product.id),
                "order_item": str(pending_order_item.id),
                "rating": 5,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_customer_cannot_submit_review_for_another_customer(
        self,
        api_client,
        customer,
        product,
        another_customer_order_item,
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(
            self.list_url,
            {
                "product": str(product.id),
                "order_item": str(another_customer_order_item.id),
                "rating": 5,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_customer_cannot_submit_duplicate_review(
        self,
        api_client,
        customer,
        product,
        delivered_order_item,
        pending_review,
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(
            self.list_url,
            {
                "product": str(product.id),
                "order_item": str(delivered_order_item.id),
                "rating": 4,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_customer_cannot_set_review_status(
        self,
        api_client,
        customer,
        product,
        delivered_order_item,
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(
            self.list_url,
            {
                "product": str(product.id),
                "order_item": str(delivered_order_item.id),
                "rating": 5,
                "status": ProductReview.Status.APPROVED,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        review = ProductReview.objects.get(
            customer=customer,
            order_item=delivered_order_item,
        )

        assert review.status == ProductReview.Status.PENDING

    def test_public_users_only_see_approved_reviews(
        self,
        api_client,
        approved_review,
        pending_review,
    ):
        response = api_client.get(self.list_url)

        ids = [item["id"] for item in response.data]

        assert str(approved_review.id) in ids
        assert str(pending_review.id) not in ids

    def test_customer_can_see_own_pending_review(
        self,
        api_client,
        customer,
        pending_review,
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.get(self.list_url)

        ids = [item["id"] for item in response.data]

        assert str(pending_review.id) in ids

    def test_customer_cannot_see_another_customers_pending_review(
        self,
        api_client,
        customer,
        another_customer,
        product,
        delivered_order_item,
        pending_review,
    ):
        # The existing pending review belongs to another customer
        # from the perspective of the second user.
        api_client.force_authenticate(user=another_customer)

        response = api_client.get(self.list_url)

        ids = [item["id"] for item in response.data]

        assert str(pending_review.id) not in ids

    def test_customer_can_retrieve_own_review(
        self,
        api_client,
        customer,
        pending_review,
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.get(
            f"{self.list_url}{pending_review.id}/"
        )

        assert response.status_code == status.HTTP_200_OK

    def test_customer_cannot_retrieve_another_customers_pending_review(
        self,
        api_client,
        another_customer,
        pending_review,
    ):
        api_client.force_authenticate(user=another_customer)

        response = api_client.get(
            f"{self.list_url}{pending_review.id}/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_customer_can_update_own_pending_review(
        self,
        api_client,
        customer,
        pending_review,
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.patch(
            f"{self.list_url}{pending_review.id}/",
            {
                "rating": 4,
                "comment": "Updated review",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        pending_review.refresh_from_db()

        assert pending_review.rating == 4
        assert pending_review.comment == "Updated review"
        assert pending_review.status == ProductReview.Status.PENDING

    def test_customer_cannot_update_approved_review(
        self,
        api_client,
        customer,
        approved_review,
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.patch(
            f"{self.list_url}{approved_review.id}/",
            {"comment": "Changed approved review"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_customer_cannot_update_another_customers_review(
        self,
        api_client,
        another_customer,
        pending_review,
    ):
        api_client.force_authenticate(user=another_customer)

        response = api_client.patch(
            f"{self.list_url}{pending_review.id}/",
            {"comment": "Unauthorized update"},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_staff_can_delete_any_review(
        self,
        api_client,
        staff_user,
        pending_review,
    ):
        api_client.force_authenticate(user=staff_user)

        response = api_client.delete(
            f"{self.list_url}{pending_review.id}/"
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        assert not ProductReview.objects.filter(
            id=pending_review.id
        ).exists()

    def test_customer_can_delete_own_review(
        self,
        api_client,
        customer,
        pending_review,
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.delete(
            f"{self.list_url}{pending_review.id}/"
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_customer_cannot_delete_another_customers_review(
        self,
        api_client,
        another_customer,
        pending_review,
    ):
        api_client.force_authenticate(user=another_customer)

        response = api_client.delete(
            f"{self.list_url}{pending_review.id}/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================
# PRODUCT-SPECIFIC REVIEW ENDPOINT TESTS
# ============================================================

@pytest.mark.django_db
class TestProductSpecificReviews:

    def test_get_reviews_for_product(
        self,
        api_client,
        product,
        approved_review,
    ):
        url = f"/api/reviews/product/{product.id}/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_only_approved_reviews_are_returned_for_product(
        self,
        api_client,
        product,
        approved_review,
        pending_review,
    ):
        url = f"/api/reviews/product/{product.id}/"

        response = api_client.get(url)

        ids = [item["id"] for item in response.data]

        assert str(approved_review.id) in ids
        assert str(pending_review.id) not in ids

    def test_product_reviews_endpoint_is_public(
        self,
        api_client,
        product,
    ):
        url = f"/api/reviews/product/{product.id}/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK


# ============================================================
# REVIEW MODERATION TESTS
# ============================================================

@pytest.mark.django_db
class TestReviewModeration:

    def test_anonymous_user_cannot_moderate_review(
        self,
        api_client,
        pending_review,
    ):
        url = f"/api/reviews/{pending_review.id}/moderate/"

        response = api_client.patch(
            url,
            {"status": ProductReview.Status.APPROVED},
            format="json",
        )

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_customer_cannot_moderate_review(
        self,
        api_client,
        customer,
        pending_review,
    ):
        api_client.force_authenticate(user=customer)

        url = f"/api/reviews/{pending_review.id}/moderate/"

        response = api_client.patch(
            url,
            {"status": ProductReview.Status.APPROVED},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_can_approve_review(
        self,
        api_client,
        staff_user,
        pending_review,
    ):
        api_client.force_authenticate(user=staff_user)

        url = f"/api/reviews/{pending_review.id}/moderate/"

        response = api_client.patch(
            url,
            {"status": ProductReview.Status.APPROVED},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        pending_review.refresh_from_db()

        assert pending_review.status == ProductReview.Status.APPROVED

    def test_staff_can_reject_review(
        self,
        api_client,
        staff_user,
        pending_review,
    ):
        api_client.force_authenticate(user=staff_user)

        url = f"/api/reviews/{pending_review.id}/moderate/"

        response = api_client.patch(
            url,
            {"status": ProductReview.Status.REJECTED},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        pending_review.refresh_from_db()

        assert pending_review.status == ProductReview.Status.REJECTED

    def test_staff_can_hide_review(
        self,
        api_client,
        staff_user,
        pending_review,
    ):
        api_client.force_authenticate(user=staff_user)

        url = f"/api/reviews/{pending_review.id}/moderate/"

        response = api_client.patch(
            url,
            {"status": ProductReview.Status.HIDDEN},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        pending_review.refresh_from_db()

        assert pending_review.status == ProductReview.Status.HIDDEN

    def test_invalid_moderation_status_is_rejected(
        self,
        api_client,
        staff_user,
        pending_review,
    ):
        api_client.force_authenticate(user=staff_user)

        url = f"/api/reviews/{pending_review.id}/moderate/"

        response = api_client.patch(
            url,
            {"status": ProductReview.Status.PENDING},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_staff_can_view_pending_reviews(
        self,
        api_client,
        staff_user,
        pending_review,
    ):
        api_client.force_authenticate(user=staff_user)

        response = api_client.get("/api/reviews/pending/")

        assert response.status_code == status.HTTP_200_OK

        ids = [item["id"] for item in response.data]

        assert str(pending_review.id) in ids

    def test_customer_cannot_view_pending_reviews(
        self,
        api_client,
        customer,
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.get("/api/reviews/pending/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_anonymous_user_cannot_view_pending_reviews(
        self,
        api_client,
    ):
        response = api_client.get("/api/reviews/pending/")

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
