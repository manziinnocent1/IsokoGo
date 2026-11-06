"""
Pytest tests for the cart app (models, serializers, viewsets).

Requirements:
    pip install pytest pytest-django

BEFORE RUNNING, edit `make_variant` below: CartItem.variant points at
"catalog.ProductVariant", and I don't know that model's required fields.

The viewsets are called directly with APIRequestFactory, so these tests do not
depend on your urls.py.
"""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from .models import Cart, CartItem
from .serializers import CartItemSerializer, CartSerializer
from .views import CartItemViewSet, CartViewSet

pytestmark = pytest.mark.django_db

PASSWORD = "Tr0ub4dor&Zebra-Lamp-92"


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def make_user():
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        n = counter["n"]
        params = {
            "email": f"customer{n}@example.com",
            "password": PASSWORD,
            "phone_number": f"0788{n:06d}",
            "first_name": "Test",
            "last_name": f"Customer{n}",
        }
        params.update(overrides)
        return get_user_model().objects.create_user(**params)

    return _make


@pytest.fixture
def user(make_user):
    return make_user()


@pytest.fixture
def other_user(make_user):
    return make_user()


@pytest.fixture
def make_variant():
    """
    EDIT ME: return a saved catalog.ProductVariant.
    Put whatever required fields your model has into `fields`.
    """
    counter = {"n": 0}
    ProductVariant = apps.get_model("catalog", "ProductVariant")

    def _make(**overrides):
        counter["n"] += 1
        n = counter["n"]
        fields = {
            # "name": f"Variant {n}",
            # "sku": f"SKU-{n}",
            # "price": Decimal("10.00"),
        }
        fields.update(overrides)
        return ProductVariant.objects.create(**fields)

    return _make


@pytest.fixture
def variant(make_variant):
    return make_variant()


@pytest.fixture
def make_cart():
    def _make(customer, **kwargs):
        return Cart.objects.create(customer=customer, **kwargs)

    return _make


@pytest.fixture
def cart(user, make_cart):
    return make_cart(user)


@pytest.fixture
def factory():
    return APIRequestFactory()


ACTIONS = {
    "list": ("get", {"get": "list"}),
    "create": ("post", {"post": "create"}),
    "retrieve": ("get", {"get": "retrieve"}),
    "update": ("put", {"put": "update"}),
    "partial_update": ("patch", {"patch": "partial_update"}),
    "destroy": ("delete", {"delete": "destroy"}),
}


@pytest.fixture
def call(factory):
    """call(CartViewSet, "create", user=u, pk=..., data={...})"""

    def _call(viewset, action, user=None, pk=None, data=None):
        http_method, mapping = ACTIONS[action]
        make = getattr(factory, http_method)
        if http_method in ("post", "put", "patch"):
            request = make("/test/", data or {}, format="json")
        else:
            request = make("/test/")
        if user is not None:
            force_authenticate(request, user=user)
        kwargs = {"pk": str(pk)} if pk is not None else {}
        return viewset.as_view(mapping)(request, **kwargs)

    return _call


def backdate(model, obj, field, minutes):
    model.objects.filter(pk=obj.pk).update(**{field: timezone.now() - timedelta(minutes=minutes)})


# ---------------------------------------------------------------------------
# Model: Cart
# ---------------------------------------------------------------------------
class TestCartModel:
    def test_defaults(self, cart):
        assert cart.status == Cart.Status.ACTIVE
        assert cart.created_at and cart.updated_at

    def test_str(self, cart):
        assert str(cart) == f"Cart {cart.id} (ACTIVE)"

    def test_only_one_active_cart_per_customer(self, user, cart):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Cart.objects.create(customer=user)

    def test_new_active_cart_allowed_after_conversion(self, user, cart):
        cart.status = Cart.Status.CONVERTED
        cart.save()
        Cart.objects.create(customer=user)
        assert Cart.objects.filter(customer=user).count() == 2

    def test_many_non_active_carts_allowed(self, user):
        Cart.objects.create(customer=user, status=Cart.Status.CONVERTED)
        Cart.objects.create(customer=user, status=Cart.Status.CONVERTED)
        Cart.objects.create(customer=user, status=Cart.Status.ABANDONED)
        assert Cart.objects.filter(customer=user).count() == 3

    def test_different_customers_can_each_have_an_active_cart(self, user, other_user, make_cart):
        make_cart(user)
        make_cart(other_user)
        assert Cart.objects.filter(status=Cart.Status.ACTIVE).count() == 2

    def test_deleting_customer_deletes_carts(self, user, cart):
        user.delete()
        assert not Cart.objects.filter(pk=cart.pk).exists()


# ---------------------------------------------------------------------------
# Model: CartItem
# ---------------------------------------------------------------------------
class TestCartItemModel:
    def test_default_quantity(self, cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant)
        item.refresh_from_db()
        assert item.quantity == Decimal("1.00")

    def test_str(self, cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant, quantity=Decimal("2.50"))
        assert str(item) == f"2.50 x {variant.pk} in cart {cart.pk}"

    def test_same_variant_twice_in_cart_rejected(self, cart, variant):
        CartItem.objects.create(cart=cart, variant=variant)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CartItem.objects.create(cart=cart, variant=variant)

    def test_same_variant_in_different_carts_allowed(self, user, other_user, make_cart, variant):
        CartItem.objects.create(cart=make_cart(user), variant=variant)
        CartItem.objects.create(cart=make_cart(other_user), variant=variant)
        assert CartItem.objects.count() == 2

    @pytest.mark.parametrize("quantity", ["0", "0.00", "-1"])
    def test_min_quantity_validator(self, cart, variant, quantity):
        item = CartItem(cart=cart, variant=variant, quantity=Decimal(quantity))
        with pytest.raises(DjangoValidationError):
            item.full_clean()

    def test_smallest_valid_quantity(self, cart, variant):
        item = CartItem(cart=cart, variant=variant, quantity=Decimal("0.01"))
        item.full_clean()

    def test_deleting_cart_deletes_items(self, cart, variant):
        CartItem.objects.create(cart=cart, variant=variant)
        cart.delete()
        assert CartItem.objects.count() == 0

    def test_variant_is_protected_from_deletion(self, cart, variant):
        CartItem.objects.create(cart=cart, variant=variant)
        with pytest.raises(ProtectedError):
            variant.delete()


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
class TestCartSerializer:
    def test_fields(self, cart):
        data = CartSerializer(cart).data
        assert set(data) == {"id", "customer", "status", "items", "total_items", "created_at", "updated_at"}

    def test_total_items_empty_cart(self, cart):
        assert CartSerializer(cart).data["total_items"] == 0

    def test_total_items_sums_quantities(self, cart, make_variant):
        CartItem.objects.create(cart=cart, variant=make_variant(), quantity=Decimal("2.00"))
        CartItem.objects.create(cart=cart, variant=make_variant(), quantity=Decimal("1.50"))
        data = CartSerializer(cart).data
        assert Decimal(str(data["total_items"])) == Decimal("3.50")
        assert len(data["items"]) == 2

    def test_all_fields_read_only(self):
        assert all(f.read_only for f in CartSerializer().fields.values())


class TestCartItemSerializer:
    def ctx(self, user):
        return {"request": SimpleNamespace(user=user)}

    def test_valid(self, user, cart, variant):
        s = CartItemSerializer(
            data={"cart": str(cart.pk), "variant": variant.pk, "quantity": "2.00"}, context=self.ctx(user)
        )
        assert s.is_valid(), s.errors

    def test_other_customers_cart_rejected(self, other_user, cart, variant):
        s = CartItemSerializer(
            data={"cart": str(cart.pk), "variant": variant.pk, "quantity": "1"}, context=self.ctx(other_user)
        )
        assert not s.is_valid()
        assert "cart" in s.errors

    @pytest.mark.parametrize("status", [Cart.Status.CONVERTED, Cart.Status.ABANDONED])
    def test_inactive_cart_rejected(self, user, cart, variant, status):
        cart.status = status
        cart.save()
        s = CartItemSerializer(
            data={"cart": str(cart.pk), "variant": variant.pk, "quantity": "1"}, context=self.ctx(user)
        )
        assert not s.is_valid()
        assert "cart" in s.errors

    @pytest.mark.parametrize("quantity", ["0", "-1", "abc", "1.005"])
    def test_bad_quantity(self, user, cart, variant, quantity):
        s = CartItemSerializer(
            data={"cart": str(cart.pk), "variant": variant.pk, "quantity": quantity}, context=self.ctx(user)
        )
        assert not s.is_valid()
        assert "quantity" in s.errors

    def test_duplicate_variant_in_cart(self, user, cart, variant):
        CartItem.objects.create(cart=cart, variant=variant)
        s = CartItemSerializer(
            data={"cart": str(cart.pk), "variant": variant.pk, "quantity": "1"}, context=self.ctx(user)
        )
        assert not s.is_valid()

    def test_read_only_fields_ignored(self, user, cart, variant):
        s = CartItemSerializer(
            data={
                "id": "00000000-0000-0000-0000-000000000000",
                "cart": str(cart.pk),
                "variant": variant.pk,
                "quantity": "1",
                "added_at": "2000-01-01T00:00:00Z",
            },
            context=self.ctx(user),
        )
        assert s.is_valid(), s.errors
        assert "id" not in s.validated_data
        assert "added_at" not in s.validated_data


# ---------------------------------------------------------------------------
# CartViewSet
# ---------------------------------------------------------------------------
class TestCartViewSet:
    @pytest.mark.parametrize("action", ["list", "create"])
    def test_collection_requires_auth(self, call, action):
        assert call(CartViewSet, action).status_code in (401, 403)

    @pytest.mark.parametrize("action", ["retrieve", "partial_update", "destroy"])
    def test_detail_requires_auth(self, call, cart, action):
        assert call(CartViewSet, action, pk=cart.pk).status_code in (401, 403)

    def test_list_returns_only_own_carts(self, call, user, other_user, make_cart):
        mine = make_cart(user, status=Cart.Status.CONVERTED)
        mine2 = make_cart(user)
        make_cart(other_user)
        resp = call(CartViewSet, "list", user=user)
        assert resp.status_code == 200
        assert {row["id"] for row in resp.data} == {str(mine.pk), str(mine2.pk)}

    def test_create(self, call, user):
        resp = call(CartViewSet, "create", user=user)
        assert resp.status_code == 201
        cart = Cart.objects.get(customer=user)
        assert cart.status == Cart.Status.ACTIVE
        assert resp.data["id"] == str(cart.pk)
        assert resp.data["customer"] == user.pk

    def test_create_ignores_client_supplied_customer_and_status(self, call, user, other_user):
        resp = call(CartViewSet, "create", user=user, data={"customer": other_user.pk, "status": "CONVERTED"})
        assert resp.status_code == 201
        cart = Cart.objects.get()
        assert cart.customer == user
        assert cart.status == Cart.Status.ACTIVE

    def test_second_active_cart_rejected(self, call, user, cart):
        resp = call(CartViewSet, "create", user=user)
        assert resp.status_code == 400
        assert Cart.objects.filter(customer=user).count() == 1

    def test_new_cart_allowed_after_previous_converted(self, call, user, cart):
        cart.status = Cart.Status.CONVERTED
        cart.save()
        resp = call(CartViewSet, "create", user=user)
        assert resp.status_code == 201
        assert Cart.objects.filter(customer=user).count() == 2

    def test_retrieve_own_cart_with_items(self, call, user, cart, variant):
        CartItem.objects.create(cart=cart, variant=variant, quantity=Decimal("3"))
        resp = call(CartViewSet, "retrieve", user=user, pk=cart.pk)
        assert resp.status_code == 200
        assert len(resp.data["items"]) == 1
        assert Decimal(str(resp.data["total_items"])) == Decimal("3")

    def test_cannot_retrieve_other_customers_cart(self, call, other_user, cart):
        assert call(CartViewSet, "retrieve", user=other_user, pk=cart.pk).status_code == 404

    def test_patch_is_blocked(self, call, user, cart):
        resp = call(CartViewSet, "partial_update", user=user, pk=cart.pk, data={"status": "CONVERTED"})
        assert resp.status_code == 400
        cart.refresh_from_db()
        assert cart.status == Cart.Status.ACTIVE

    def test_put_cannot_change_cart(self, call, user, other_user, cart):
        call(CartViewSet, "update", user=user, pk=cart.pk, data={"status": "CONVERTED", "customer": other_user.pk})
        cart.refresh_from_db()
        assert cart.status == Cart.Status.ACTIVE
        assert cart.customer == user

    def test_destroy_own_cart(self, call, user, cart, variant):
        CartItem.objects.create(cart=cart, variant=variant)
        resp = call(CartViewSet, "destroy", user=user, pk=cart.pk)
        assert resp.status_code == 204
        assert not Cart.objects.filter(pk=cart.pk).exists()
        assert CartItem.objects.count() == 0

    def test_cannot_destroy_other_customers_cart(self, call, other_user, cart):
        assert call(CartViewSet, "destroy", user=other_user, pk=cart.pk).status_code == 404
        assert Cart.objects.filter(pk=cart.pk).exists()


# ---------------------------------------------------------------------------
# CartItemViewSet
# ---------------------------------------------------------------------------
class TestCartItemViewSet:
    @pytest.mark.parametrize("action", ["list", "create"])
    def test_collection_requires_auth(self, call, action):
        assert call(CartItemViewSet, action).status_code in (401, 403)

    @pytest.mark.parametrize("action", ["retrieve", "update", "partial_update", "destroy"])
    def test_detail_requires_auth(self, call, cart, variant, action):
        item = CartItem.objects.create(cart=cart, variant=variant)
        assert call(CartItemViewSet, action, pk=item.pk).status_code in (401, 403)

    # -- list / retrieve ----------------------------------------------------
    def test_list_only_own_items_newest_first(self, call, user, other_user, cart, make_cart, make_variant):
        old = CartItem.objects.create(cart=cart, variant=make_variant())
        new = CartItem.objects.create(cart=cart, variant=make_variant())
        backdate(CartItem, old, "added_at", 30)
        backdate(CartItem, new, "added_at", 1)
        CartItem.objects.create(cart=make_cart(other_user), variant=make_variant())

        resp = call(CartItemViewSet, "list", user=user)
        assert resp.status_code == 200
        assert [row["id"] for row in resp.data] == [str(new.pk), str(old.pk)]

    def test_retrieve_own_item(self, call, user, cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant, quantity=Decimal("2"))
        resp = call(CartItemViewSet, "retrieve", user=user, pk=item.pk)
        assert resp.status_code == 200
        assert resp.data["id"] == str(item.pk)
        assert Decimal(resp.data["quantity"]) == Decimal("2")

    def test_cannot_retrieve_other_customers_item(self, call, other_user, cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant)
        assert call(CartItemViewSet, "retrieve", user=other_user, pk=item.pk).status_code == 404

    # -- create ---------------------------------------------------------------
    def test_create(self, call, user, cart, variant):
        resp = call(
            CartItemViewSet,
            "create",
            user=user,
            data={"cart": str(cart.pk), "variant": variant.pk, "quantity": "2.50"},
        )
        assert resp.status_code == 201
        item = CartItem.objects.get()
        assert item.cart == cart and item.variant == variant
        assert item.quantity == Decimal("2.50")

    def test_create_default_quantity(self, call, user, cart, variant):
        resp = call(CartItemViewSet, "create", user=user, data={"cart": str(cart.pk), "variant": variant.pk})
        assert resp.status_code == 201
        assert CartItem.objects.get().quantity == Decimal("1.00")

    def test_cannot_add_to_other_customers_cart(self, call, other_user, cart, variant):
        resp = call(
            CartItemViewSet,
            "create",
            user=other_user,
            data={"cart": str(cart.pk), "variant": variant.pk, "quantity": "1"},
        )
        assert resp.status_code == 400
        assert CartItem.objects.count() == 0

    @pytest.mark.parametrize("status", [Cart.Status.CONVERTED, Cart.Status.ABANDONED])
    def test_cannot_add_to_inactive_cart(self, call, user, cart, variant, status):
        cart.status = status
        cart.save()
        resp = call(
            CartItemViewSet, "create", user=user, data={"cart": str(cart.pk), "variant": variant.pk, "quantity": "1"}
        )
        assert resp.status_code == 400
        assert CartItem.objects.count() == 0

    def test_duplicate_variant_rejected(self, call, user, cart, variant):
        CartItem.objects.create(cart=cart, variant=variant)
        resp = call(
            CartItemViewSet, "create", user=user, data={"cart": str(cart.pk), "variant": variant.pk, "quantity": "1"}
        )
        assert resp.status_code == 400
        assert CartItem.objects.count() == 1

    @pytest.mark.parametrize("quantity", ["0", "-2", "abc"])
    def test_invalid_quantity_rejected(self, call, user, cart, variant, quantity):
        resp = call(
            CartItemViewSet,
            "create",
            user=user,
            data={"cart": str(cart.pk), "variant": variant.pk, "quantity": quantity},
        )
        assert resp.status_code == 400
        assert CartItem.objects.count() == 0

    def test_missing_cart_or_variant(self, call, user, cart, variant):
        assert call(CartItemViewSet, "create", user=user, data={"variant": variant.pk}).status_code == 400
        assert call(CartItemViewSet, "create", user=user, data={"cart": str(cart.pk)}).status_code == 400

    def test_nonexistent_cart(self, call, user, variant):
        resp = call(
            CartItemViewSet,
            "create",
            user=user,
            data={"cart": "00000000-0000-0000-0000-000000000000", "variant": variant.pk},
        )
        assert resp.status_code == 400

    # -- update ---------------------------------------------------------------
    def test_patch_quantity(self, call, user, cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant)
        resp = call(CartItemViewSet, "partial_update", user=user, pk=item.pk, data={"quantity": "5.00"})
        assert resp.status_code == 200
        item.refresh_from_db()
        assert item.quantity == Decimal("5.00")

    def test_put_updates_item(self, call, user, cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant)
        resp = call(
            CartItemViewSet,
            "update",
            user=user,
            pk=item.pk,
            data={"cart": str(cart.pk), "variant": variant.pk, "quantity": "7.00"},
        )
        assert resp.status_code == 200
        item.refresh_from_db()
        assert item.quantity == Decimal("7.00")

    def test_patch_invalid_quantity(self, call, user, cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant, quantity=Decimal("2"))
        resp = call(CartItemViewSet, "partial_update", user=user, pk=item.pk, data={"quantity": "0"})
        assert resp.status_code == 400
        item.refresh_from_db()
        assert item.quantity == Decimal("2")

    def test_cannot_update_item_in_inactive_cart(self, call, user, cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant, quantity=Decimal("2"))
        cart.status = Cart.Status.CONVERTED
        cart.save()
        resp = call(CartItemViewSet, "partial_update", user=user, pk=item.pk, data={"quantity": "9"})
        assert resp.status_code == 400
        item.refresh_from_db()
        assert item.quantity == Decimal("2")

    def test_cannot_update_other_customers_item(self, call, other_user, cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant)
        resp = call(CartItemViewSet, "partial_update", user=other_user, pk=item.pk, data={"quantity": "9"})
        assert resp.status_code == 404

    def test_cannot_move_item_into_other_customers_cart(self, call, user, other_user, cart, make_cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant)
        their_cart = make_cart(other_user)
        resp = call(CartItemViewSet, "partial_update", user=user, pk=item.pk, data={"cart": str(their_cart.pk)})
        assert resp.status_code == 400
        item.refresh_from_db()
        assert item.cart == cart

    # -- delete ---------------------------------------------------------------
    def test_destroy(self, call, user, cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant)
        resp = call(CartItemViewSet, "destroy", user=user, pk=item.pk)
        assert resp.status_code == 204
        assert not CartItem.objects.filter(pk=item.pk).exists()

    def test_cannot_destroy_item_in_inactive_cart(self, call, user, cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant)
        cart.status = Cart.Status.CONVERTED
        cart.save()
        resp = call(CartItemViewSet, "destroy", user=user, pk=item.pk)
        assert resp.status_code == 400
        assert CartItem.objects.filter(pk=item.pk).exists()

    def test_cannot_destroy_other_customers_item(self, call, other_user, cart, variant):
        item = CartItem.objects.create(cart=cart, variant=variant)
        assert call(CartItemViewSet, "destroy", user=other_user, pk=item.pk).status_code == 404
        assert CartItem.objects.filter(pk=item.pk).exists()