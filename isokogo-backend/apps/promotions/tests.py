
import pytest

from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import Coupon, CouponUsage, Promotion
from .serializers import (
    CouponSerializer,
    CouponValidationInputSerializer,
    PromotionSerializer,
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
        email="admin@example.com",
        password="AdminPassword123!",
        is_staff=True,
    )


@pytest.fixture
def active_coupon(db):
    now = timezone.now()

    return Coupon.objects.create(
        code="SAVE20",
        description="Get 20 percent off",
        discount_type=Coupon.DiscountType.PERCENTAGE,
        discount_value=Decimal("20.00"),
        minimum_order_amount=Decimal("10.00"),
        maximum_discount=Decimal("50.00"),
        usage_limit=100,
        usage_per_customer=2,
        start_date=now - timedelta(days=1),
        expiry_date=now + timedelta(days=30),
        is_active=True,
    )


@pytest.fixture
def inactive_coupon(db):
    now = timezone.now()

    return Coupon.objects.create(
        code="INACTIVE10",
        discount_type=Coupon.DiscountType.FIXED,
        discount_value=Decimal("10.00"),
        start_date=now - timedelta(days=5),
        expiry_date=now + timedelta(days=30),
        is_active=False,
    )


@pytest.fixture
def expired_coupon(db):
    now = timezone.now()

    return Coupon.objects.create(
        code="EXPIRED10",
        discount_type=Coupon.DiscountType.FIXED,
        discount_value=Decimal("10.00"),
        start_date=now - timedelta(days=30),
        expiry_date=now - timedelta(days=1),
        is_active=True,
    )


@pytest.fixture
def future_coupon(db):
    now = timezone.now()

    return Coupon.objects.create(
        code="FUTURE10",
        discount_type=Coupon.DiscountType.FIXED,
        discount_value=Decimal("10.00"),
        start_date=now + timedelta(days=5),
        expiry_date=now + timedelta(days=30),
        is_active=True,
    )


@pytest.fixture
def active_promotion(db):
    now = timezone.now()

    return Promotion.objects.create(
        name="Weekend Special",
        description="Special weekend discounts",
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=7),
        status=Promotion.Status.ACTIVE,
        is_active=True,
    )


@pytest.fixture
def draft_promotion(db):
    now = timezone.now()

    return Promotion.objects.create(
        name="Upcoming Promotion",
        description="Promotion coming soon",
        start_date=now + timedelta(days=5),
        end_date=now + timedelta(days=10),
        status=Promotion.Status.DRAFT,
        is_active=True,
    )


# ============================================================
# COUPON MODEL TESTS
# ============================================================

@pytest.mark.django_db
class TestCouponModel:

    def test_coupon_creation(self, active_coupon):
        assert active_coupon.code == "SAVE20"
        assert active_coupon.discount_type == Coupon.DiscountType.PERCENTAGE
        assert active_coupon.discount_value == Decimal("20.00")

    def test_coupon_string_representation(self, active_coupon):
        assert str(active_coupon) == "SAVE20"

    def test_coupon_uuid_primary_key(self, active_coupon):
        assert active_coupon.id is not None

    def test_active_coupon_is_valid(self, active_coupon):
        assert active_coupon.is_valid is True

    def test_inactive_coupon_is_invalid(self, inactive_coupon):
        assert inactive_coupon.is_valid is False

    def test_expired_coupon_is_invalid(self, expired_coupon):
        assert expired_coupon.is_valid is False

    def test_future_coupon_is_invalid(self, future_coupon):
        assert future_coupon.is_valid is False

    def test_coupon_default_usage_per_customer(self, db):
        now = timezone.now()

        coupon = Coupon.objects.create(
            code="DEFAULT10",
            discount_type=Coupon.DiscountType.FIXED,
            discount_value=Decimal("10.00"),
            start_date=now,
            expiry_date=now + timedelta(days=10),
        )

        assert coupon.usage_per_customer == 1


# ============================================================
# COUPON SERIALIZER TESTS
# ============================================================

@pytest.mark.django_db
class TestCouponSerializer:

    def test_valid_coupon_serialization(self, active_coupon):
        serializer = CouponSerializer(active_coupon)

        assert serializer.data["code"] == "SAVE20"
        assert serializer.data["discount_value"] == "20.00"
        assert serializer.data["is_valid"] is True

    def test_coupon_code_is_converted_to_uppercase(self):
        serializer = CouponSerializer(data={
            "code": "save50",
            "discount_type": Coupon.DiscountType.FIXED,
            "discount_value": "50.00",
            "start_date": timezone.now(),
            "expiry_date": timezone.now() + timedelta(days=10),
        })

        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["code"] == "SAVE50"

    def test_duplicate_coupon_code_is_rejected(self, active_coupon):
        serializer = CouponSerializer(data={
            "code": "save20",
            "discount_type": Coupon.DiscountType.FIXED,
            "discount_value": "10.00",
            "start_date": timezone.now(),
            "expiry_date": timezone.now() + timedelta(days=10),
        })

        assert serializer.is_valid() is False
        assert "code" in serializer.errors

    def test_coupon_code_can_be_updated_without_duplicate_error(
        self, active_coupon
    ):
        serializer = CouponSerializer(
            active_coupon,
            data={"code": "SAVE20"},
            partial=True,
        )

        assert serializer.is_valid(), serializer.errors

    def test_percentage_discount_cannot_exceed_100(self):
        serializer = CouponSerializer(data={
            "code": "SAVE150",
            "discount_type": Coupon.DiscountType.PERCENTAGE,
            "discount_value": "150.00",
            "start_date": timezone.now(),
            "expiry_date": timezone.now() + timedelta(days=10),
        })

        assert serializer.is_valid() is False
        assert "discount_value" in serializer.errors

    def test_percentage_discount_of_100_is_valid(self):
        serializer = CouponSerializer(data={
            "code": "SAVE100",
            "discount_type": Coupon.DiscountType.PERCENTAGE,
            "discount_value": "100.00",
            "start_date": timezone.now(),
            "expiry_date": timezone.now() + timedelta(days=10),
        })

        assert serializer.is_valid(), serializer.errors

    def test_expiry_date_must_be_after_start_date(self):
        now = timezone.now()

        serializer = CouponSerializer(data={
            "code": "INVALIDDATE",
            "discount_type": Coupon.DiscountType.FIXED,
            "discount_value": "10.00",
            "start_date": now,
            "expiry_date": now - timedelta(days=1),
        })

        assert serializer.is_valid() is False
        assert "expiry_date" in serializer.errors


# ============================================================
# COUPON VALIDATION INPUT SERIALIZER TESTS
# ============================================================

@pytest.mark.django_db
class TestCouponValidationInputSerializer:

    def test_valid_input(self):
        serializer = CouponValidationInputSerializer(data={
            "code": "SAVE20",
            "order_amount": "100.00",
        })

        assert serializer.is_valid(), serializer.errors

    def test_missing_coupon_code(self):
        serializer = CouponValidationInputSerializer(data={
            "order_amount": "100.00",
        })

        assert serializer.is_valid() is False
        assert "code" in serializer.errors

    def test_missing_order_amount(self):
        serializer = CouponValidationInputSerializer(data={
            "code": "SAVE20",
        })

        assert serializer.is_valid() is False
        assert "order_amount" in serializer.errors

    def test_zero_order_amount_is_invalid(self):
        serializer = CouponValidationInputSerializer(data={
            "code": "SAVE20",
            "order_amount": "0.00",
        })

        assert serializer.is_valid() is False

    def test_negative_order_amount_is_invalid(self):
        serializer = CouponValidationInputSerializer(data={
            "code": "SAVE20",
            "order_amount": "-10.00",
        })

        assert serializer.is_valid() is False


# ============================================================
# COUPON API TESTS
# ============================================================

@pytest.mark.django_db
class TestCouponAPI:

    list_url = "/api/promotions/coupons/"

    validate_url = "/api/promotions/coupons/validate/"

    def test_anonymous_user_can_view_valid_coupons(
        self, api_client, active_coupon
    ):
        response = api_client.get(self.list_url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["code"] == "SAVE20"

    def test_customers_cannot_see_inactive_coupons(
        self, api_client, active_coupon, inactive_coupon
    ):
        response = api_client.get(self.list_url)

        codes = [item["code"] for item in response.data]

        assert "SAVE20" in codes
        assert "INACTIVE10" not in codes

    def test_customers_cannot_see_expired_coupons(
        self, api_client, active_coupon, expired_coupon
    ):
        response = api_client.get(self.list_url)

        codes = [item["code"] for item in response.data]

        assert "EXPIRED10" not in codes

    def test_customers_cannot_see_future_coupons(
        self, api_client, active_coupon, future_coupon
    ):
        response = api_client.get(self.list_url)

        codes = [item["code"] for item in response.data]

        assert "FUTURE10" not in codes

    def test_staff_can_view_all_coupons(
        self,
        api_client,
        staff_user,
        active_coupon,
        inactive_coupon,
        expired_coupon,
        future_coupon,
    ):
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(self.list_url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 4

    def test_anonymous_user_cannot_create_coupon(self, api_client):
        response = api_client.post(self.list_url, {
            "code": "NEW10",
            "discount_type": Coupon.DiscountType.FIXED,
            "discount_value": "10.00",
            "start_date": timezone.now().isoformat(),
            "expiry_date": (
                timezone.now() + timedelta(days=10)
            ).isoformat(),
        })

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_customer_cannot_create_coupon(
        self, api_client, customer
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(self.list_url, {
            "code": "NEW10",
            "discount_type": Coupon.DiscountType.FIXED,
            "discount_value": "10.00",
            "start_date": timezone.now().isoformat(),
            "expiry_date": (
                timezone.now() + timedelta(days=10)
            ).isoformat(),
        })

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_can_create_coupon(self, api_client, staff_user):
        api_client.force_authenticate(user=staff_user)

        response = api_client.post(self.list_url, {
            "code": "STAFF20",
            "description": "Staff-created coupon",
            "discount_type": Coupon.DiscountType.PERCENTAGE,
            "discount_value": "20.00",
            "minimum_order_amount": "10.00",
            "usage_limit": 100,
            "usage_per_customer": 1,
            "start_date": timezone.now().isoformat(),
            "expiry_date": (
                timezone.now() + timedelta(days=10)
            ).isoformat(),
            "is_active": True,
        }, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert Coupon.objects.filter(code="STAFF20").exists()


# ============================================================
# COUPON VALIDATION API TESTS
# ============================================================

@pytest.mark.django_db
class TestCouponValidationAPI:

    validate_url = "/api/promotions/coupons/validate/"

    def test_anonymous_user_cannot_validate_coupon(
        self, api_client, active_coupon
    ):
        response = api_client.post(self.validate_url, {
            "code": "SAVE20",
            "order_amount": "100.00",
        })

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_valid_percentage_coupon(
        self, api_client, customer, active_coupon
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(self.validate_url, {
            "code": "SAVE20",
            "order_amount": "100.00",
        }, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["valid"] is True
        assert response.data["discount_amount"] == "20.00"
        assert response.data["final_subtotal"] == "80.00"

    def test_coupon_code_is_case_insensitive(
        self, api_client, customer, active_coupon
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(self.validate_url, {
            "code": "save20",
            "order_amount": "100.00",
        }, format="json")

        assert response.data["valid"] is True

    def test_nonexistent_coupon(
        self, api_client, customer
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(self.validate_url, {
            "code": "DOESNOTEXIST",
            "order_amount": "100.00",
        }, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["valid"] is False

    def test_inactive_coupon(
        self, api_client, customer, inactive_coupon
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(self.validate_url, {
            "code": "INACTIVE10",
            "order_amount": "100.00",
        }, format="json")

        assert response.data["valid"] is False
        assert response.data["message"] == "This coupon is inactive."

    def test_expired_coupon(
        self, api_client, customer, expired_coupon
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(self.validate_url, {
            "code": "EXPIRED10",
            "order_amount": "100.00",
        }, format="json")

        assert response.data["valid"] is False
        assert response.data["message"] == "This coupon has expired."

    def test_future_coupon(
        self, api_client, customer, future_coupon
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(self.validate_url, {
            "code": "FUTURE10",
            "order_amount": "100.00",
        }, format="json")

        assert response.data["valid"] is False
        assert response.data["message"] == "This coupon is not active yet."

    def test_minimum_order_amount(
        self, api_client, customer, active_coupon
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(self.validate_url, {
            "code": "SAVE20",
            "order_amount": "5.00",
        }, format="json")

        assert response.data["valid"] is False
        assert "Minimum order amount" in response.data["message"]

    def test_percentage_discount_maximum_cap(
        self, api_client, customer, active_coupon
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(self.validate_url, {
            "code": "SAVE20",
            "order_amount": "500.00",
        }, format="json")

        assert response.data["valid"] is True
        assert response.data["discount_amount"] == "50.00"
        assert response.data["final_subtotal"] == "450.00"

    def test_fixed_discount_coupon(
        self, api_client, customer, db
    ):
        now = timezone.now()

        Coupon.objects.create(
            code="FIXED10",
            discount_type=Coupon.DiscountType.FIXED,
            discount_value=Decimal("10.00"),
            start_date=now - timedelta(days=1),
            expiry_date=now + timedelta(days=10),
        )

        api_client.force_authenticate(user=customer)

        response = api_client.post(self.validate_url, {
            "code": "FIXED10",
            "order_amount": "100.00",
        }, format="json")

        assert response.data["valid"] is True
        assert response.data["discount_amount"] == "10.00"
        assert response.data["final_subtotal"] == "90.00"

    def test_fixed_discount_cannot_exceed_order_amount(
        self, api_client, customer, db
    ):
        now = timezone.now()

        Coupon.objects.create(
            code="FIXED50",
            discount_type=Coupon.DiscountType.FIXED,
            discount_value=Decimal("50.00"),
            start_date=now - timedelta(days=1),
            expiry_date=now + timedelta(days=10),
        )

        api_client.force_authenticate(user=customer)

        response = api_client.post(self.validate_url, {
            "code": "FIXED50",
            "order_amount": "20.00",
        }, format="json")

        assert response.data["discount_amount"] == "20.00"
        assert response.data["final_subtotal"] == "0.00"

    def test_free_delivery_coupon(
        self, api_client, customer, db
    ):
        now = timezone.now()

        Coupon.objects.create(
            code="FREEDELIVERY",
            discount_type=Coupon.DiscountType.FREE_DELIVERY,
            discount_value=Decimal("0.00"),
            start_date=now - timedelta(days=1),
            expiry_date=now + timedelta(days=10),
        )

        api_client.force_authenticate(user=customer)

        response = api_client.post(self.validate_url, {
            "code": "FREEDELIVERY",
            "order_amount": "100.00",
        }, format="json")

        assert response.data["valid"] is True
        assert response.data["free_delivery"] is True
        assert response.data["discount_amount"] == "0.00"

    def test_overall_usage_limit_reached(
        self, api_client, customer, active_coupon, monkeypatch
    ):
        api_client.force_authenticate(user=customer)

        monkeypatch.setattr(
            "apps.promotions.views.CouponUsage.objects.filter",
            lambda **kwargs: type(
                "MockQuerySet",
                (),
                {"count": lambda self: 100}
            )(),
        )

        response = api_client.post(self.validate_url, {
            "code": "SAVE20",
            "order_amount": "100.00",
        }, format="json")

        assert response.data["valid"] is False
        assert response.data["message"] == (
            "This coupon has reached its usage limit."
        )

    def test_customer_usage_limit_reached(
        self, api_client, customer, active_coupon, monkeypatch
    ):
        api_client.force_authenticate(user=customer)

        def mocked_filter(**kwargs):
            count = 0

            if kwargs.get("coupon") == active_coupon:
                count = 0

            if kwargs.get("customer") == customer:
                count = 2

            return type(
                "MockQuerySet",
                (),
                {"count": lambda self: count}
            )()

        monkeypatch.setattr(
            "apps.promotions.views.CouponUsage.objects.filter",
            mocked_filter,
        )

        response = api_client.post(self.validate_url, {
            "code": "SAVE20",
            "order_amount": "100.00",
        }, format="json")

        assert response.data["valid"] is False
        assert "maximum number of times" in response.data["message"]


# ============================================================
# COUPON USAGE API TESTS
# ============================================================

@pytest.mark.django_db
class TestCouponUsageAPI:

    list_url = "/api/promotions/coupon-usages/"

    def test_anonymous_user_cannot_view_usage(self, api_client):
        response = api_client.get(self.list_url)

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_customer_can_view_own_usage(
        self, api_client, customer
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.get(self.list_url)

        assert response.status_code == status.HTTP_200_OK

    def test_staff_can_view_coupon_usage(
        self, api_client, staff_user
    ):
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(self.list_url)

        assert response.status_code == status.HTTP_200_OK

    def test_coupon_usage_is_read_only(
        self, api_client, customer
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(self.list_url, {})

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ============================================================
# PROMOTION MODEL TESTS
# ============================================================

@pytest.mark.django_db
class TestPromotionModel:

    def test_promotion_creation(self, active_promotion):
        assert active_promotion.name == "Weekend Special"
        assert active_promotion.status == Promotion.Status.ACTIVE

    def test_promotion_string_representation(self, active_promotion):
        assert str(active_promotion) == "Weekend Special"

    def test_active_promotion_is_currently_active(
        self, active_promotion
    ):
        assert active_promotion.is_currently_active is True

    def test_draft_promotion_is_not_currently_active(
        self, draft_promotion
    ):
        assert draft_promotion.is_currently_active is False

    def test_inactive_promotion_is_not_currently_active(
        self, active_promotion
    ):
        active_promotion.is_active = False
        active_promotion.save()

        assert active_promotion.is_currently_active is False


# ============================================================
# PROMOTION SERIALIZER TESTS
# ============================================================

@pytest.mark.django_db
class TestPromotionSerializer:

    def test_valid_promotion_serialization(self, active_promotion):
        serializer = PromotionSerializer(active_promotion)

        assert serializer.data["name"] == "Weekend Special"
        assert serializer.data["is_currently_active"] is True

    def test_promotion_end_date_must_be_after_start_date(self):
        now = timezone.now()

        serializer = PromotionSerializer(data={
            "name": "Invalid Promotion",
            "start_date": now,
            "end_date": now - timedelta(days=1),
            "status": Promotion.Status.DRAFT,
            "is_active": True,
        })

        assert serializer.is_valid() is False
        assert "end_date" in serializer.errors


# ============================================================
# PROMOTION API TESTS
# ============================================================

@pytest.mark.django_db
class TestPromotionAPI:

    list_url = "/api/promotions/promotions/"

    current_url = "/api/promotions/promotions/current/"

    def test_anonymous_user_can_view_promotions(
        self, api_client, active_promotion
    ):
        response = api_client.get(self.list_url)

        assert response.status_code == status.HTTP_200_OK

    def test_customers_only_see_active_promotions(
        self,
        api_client,
        active_promotion,
        draft_promotion,
    ):
        response = api_client.get(self.list_url)

        names = [item["name"] for item in response.data]

        assert "Weekend Special" in names
        assert "Upcoming Promotion" not in names

    def test_current_endpoint_is_public(
        self, api_client, active_promotion
    ):
        response = api_client.get(self.current_url)

        assert response.status_code == status.HTTP_200_OK

    def test_current_endpoint_returns_active_promotions(
        self,
        api_client,
        active_promotion,
        draft_promotion,
    ):
        response = api_client.get(self.current_url)

        names = [item["name"] for item in response.data]

        assert "Weekend Special" in names
        assert "Upcoming Promotion" not in names

    def test_staff_can_view_all_promotions(
        self,
        api_client,
        staff_user,
        active_promotion,
        draft_promotion,
    ):
        api_client.force_authenticate(user=staff_user)

        response = api_client.get(self.list_url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_customer_cannot_create_promotion(
        self, api_client, customer
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.post(self.list_url, {
            "name": "New Promotion",
            "start_date": timezone.now().isoformat(),
            "end_date": (
                timezone.now() + timedelta(days=10)
            ).isoformat(),
        }, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_can_create_promotion(
        self, api_client, staff_user
    ):
        api_client.force_authenticate(user=staff_user)

        response = api_client.post(self.list_url, {
            "name": "New Promotion",
            "description": "New product discounts",
            "start_date": timezone.now().isoformat(),
            "end_date": (
                timezone.now() + timedelta(days=10)
            ).isoformat(),
            "status": Promotion.Status.DRAFT,
            "is_active": True,
        }, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert Promotion.objects.filter(
            name="New Promotion"
        ).exists()

    def test_customer_cannot_delete_promotion(
        self, api_client, customer, active_promotion
    ):
        api_client.force_authenticate(user=customer)

        response = api_client.delete(
            f"{self.list_url}{active_promotion.id}/"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_can_delete_promotion(
        self, api_client, staff_user, active_promotion
    ):
        api_client.force_authenticate(user=staff_user)

        response = api_client.delete(
            f"{self.list_url}{active_promotion.id}/"
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Promotion.objects.filter(
            id=active_promotion.id
        ).exists()
