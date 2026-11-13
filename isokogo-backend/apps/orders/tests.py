import re
from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    OrderSubstitution,
)

User = get_user_model()


# =====================================================
# URL NAMES
# These viewsets define `queryset`, so the router derives basenames from the
# model name (lower-cased, no hyphens). If you passed explicit basenames when
# registering, change the constants below to match.
# =====================================================

ORDER_LIST = "order-list"
ORDER_DETAIL = "order-detail"
ORDER_UPDATE_STATUS = "order-update-status"
ORDER_CANCEL = "order-cancel"

ITEM_LIST = "orderitem-list"
ITEM_DETAIL = "orderitem-detail"

HISTORY_LIST = "orderstatushistory-list"
HISTORY_DETAIL = "orderstatushistory-detail"

SUB_LIST = "ordersubstitution-list"
SUB_DETAIL = "ordersubstitution-detail"
SUB_RESPOND = "ordersubstitution-respond"

UNAUTHORIZED = [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
MISSING_UUID = "00000000-0000-0000-0000-000000000000"

S = Order.Status


# =====================================================
# HELPERS
# =====================================================

# TODO: add whatever catalog.Product / catalog.ProductVariant need to be
# created beyond the fields filled in below (categories, brands, etc.).
# Assumed fields: Product(name, is_available),
# ProductVariant(product, name, sku, selling_price, is_active).
PRODUCT_DEFAULTS = {}
VARIANT_DEFAULTS = {}

_c = {"user": 0, "product": 0, "variant": 0, "order": 0}


def create_user(prefix="user", is_staff=False, password="StrongPass123!"):
    _c["user"] += 1
    username = f"{prefix}{_c['user']}"
    try:
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password=password,
            is_staff=is_staff,
        )
    except TypeError:
        # custom user model without a username field
        return User.objects.create_user(
            email=f"{username}@example.com",
            password=password,
            is_staff=is_staff,
        )


def make_product(**overrides):
    Product = apps.get_model("catalog", "Product")
    _c["product"] += 1
    data = {"name": f"Product {_c['product']}", "is_available": True}
    data.update(PRODUCT_DEFAULTS)
    data.update(overrides)
    return Product.objects.create(**data)


def make_variant(product=None, price="10.00", **overrides):
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    _c["variant"] += 1
    n = _c["variant"]
    data = {
        "product": product or make_product(),
        "name": f"Variant {n}",
        "sku": f"SKU-{n:05d}",
        "selling_price": Decimal(price),
        "is_active": True,
    }
    data.update(VARIANT_DEFAULTS)
    data.update(overrides)
    return ProductVariant.objects.create(**data)


def make_address(user, **overrides):
    Profile = apps.get_model("customers", "CustomerProfile")
    Address = apps.get_model("customers", "CustomerAddress")
    profile, _ = Profile.objects.get_or_create(user=user)
    data = {
        "address_name": "Home",
        "recipient_name": "Jane Doe",
        "recipient_phone_number": "+250788000000",
        "province": "Kigali",
        "district": "Gasabo",
        "sector": "Kimironko",
        "cell": "Bibare",
        "village": "Kamatamu",
        "street_address": "KG 11 Ave",
        "delivery_instructions": "Call on arrival",
    }
    data.update(overrides)
    return Address.objects.create(customer=profile, **data)


def create_order(customer, order_status=S.PENDING, **overrides):
    _c["order"] += 1
    data = {"order_number": f"ORD-TEST-{_c['order']:05d}", "status": order_status}
    data.update(overrides)
    return Order.objects.create(customer=customer, **data)


def create_item(order, variant=None, quantity="2.00", unit_price=None):
    variant = variant or make_variant()
    return OrderItem.objects.create(
        order=order,
        product=variant.product,
        variant=variant,
        product_name=variant.product.name,
        variant_name=variant.name,
        sku=variant.sku,
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price) if unit_price is not None else variant.selling_price,
    )


def create_substitution(item, suggested=None, sub_status=OrderSubstitution.Status.PENDING):
    return OrderSubstitution.objects.create(
        order_item=item,
        requested_variant=item.variant,
        suggested_variant=suggested or make_variant(),
        status=sub_status,
    )


def results(response):
    data = response.data
    return data["results"] if isinstance(data, dict) and "results" in data else data


def ids(response):
    return {str(row["id"]) for row in results(response)}


def dec(value):
    return Decimal(str(value))


# =====================================================
# MODEL TESTS
# =====================================================

class OrderModelTests(APITestCase):

    def setUp(self):
        self.user = create_user("owner")

    def test_order_defaults_and_str(self):
        order = create_order(self.user)
        self.assertEqual(order.status, S.PENDING)
        self.assertEqual(order.subtotal, Decimal("0.00"))
        self.assertEqual(order.total_amount, Decimal("0.00"))
        self.assertEqual(order.delivery_address_snapshot, {})
        self.assertEqual(str(order), order.order_number)

    def test_order_number_unique(self):
        order = create_order(self.user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_order(self.user, order_number=order.order_number)

    def test_orders_newest_first(self):
        first = create_order(self.user)
        second = create_order(self.user)
        self.assertEqual(list(Order.objects.all()), [second, first])

    def test_customer_with_orders_is_protected(self):
        create_order(self.user)
        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_address_deletion_keeps_order(self):
        address = make_address(self.user)
        order = create_order(self.user, delivery_address=address)
        address.delete()
        order.refresh_from_db()
        self.assertIsNone(order.delivery_address)

    def test_item_subtotal_and_str(self):
        item = create_item(create_order(self.user), quantity="1.50", unit_price="3.33")
        self.assertEqual(item.subtotal, Decimal("5.00"))  # 4.995 -> 5.00
        self.assertTrue(str(item).startswith("1.50 x "))

    def test_item_subtotal_recalculated_on_save(self):
        item = create_item(create_order(self.user), quantity="2.00", unit_price="5.00")
        item.quantity = Decimal("4.00")
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.subtotal, Decimal("20.00"))

    def test_deleting_order_cascades(self):
        order = create_order(self.user)
        item = create_item(order)
        create_substitution(item)
        OrderStatusHistory.objects.create(order=order, new_status=S.PENDING)

        order.delete()

        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(OrderSubstitution.objects.count(), 0)
        self.assertEqual(OrderStatusHistory.objects.count(), 0)

    def test_history_oldest_first_and_str(self):
        order = create_order(self.user)
        first = OrderStatusHistory.objects.create(order=order, new_status=S.PENDING)
        second = OrderStatusHistory.objects.create(
            order=order, previous_status=S.PENDING, new_status=S.CONFIRMED
        )
        self.assertEqual(list(order.status_history.all()), [first, second])
        self.assertIn("- -> PENDING", str(first))
        self.assertIn("PENDING -> CONFIRMED", str(second))

    def test_substitution_defaults(self):
        substitution = create_substitution(create_item(create_order(self.user)))
        self.assertEqual(substitution.status, OrderSubstitution.Status.PENDING)
        self.assertEqual(substitution.customer_response, "")
        self.assertIn("PENDING", str(substitution))


# =====================================================
# ORDER CREATE TESTS
# =====================================================

class OrderCreateTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)
        self.v1 = make_variant(price="10.00")
        self.v2 = make_variant(price="3.50")
        self.url = reverse(ORDER_LIST)
        self.client.force_authenticate(self.user)

    def _payload(self, **overrides):
        data = {
            "order_items": [{"variant": str(self.v1.pk), "quantity": "2.00"}],
            "customer_notes": "Please ring the bell",
        }
        data.update(overrides)
        return data

    def test_unauthenticated_denied(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_create_order(self):
        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.customer, self.user)
        self.assertEqual(order.status, S.PENDING)
        self.assertEqual(order.customer_notes, "Please ring the bell")
        self.assertRegex(order.order_number, r"^ORD-[A-Z0-9]{12}$")
        self.assertEqual(order.delivery_address_snapshot, {})

    def test_totals_are_calculated_server_side(self):
        payload = self._payload(
            order_items=[
                {"variant": str(self.v1.pk), "quantity": "2.00"},
                {"variant": str(self.v2.pk), "quantity": "1.50"},
            ]
        )

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.subtotal, Decimal("25.25"))  # 20.00 + 5.25
        self.assertEqual(order.total_amount, Decimal("25.25"))
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(response.data["item_count"], 2)

    def test_items_snapshot_product_details(self):
        response = self.client.post(self.url, self._payload(), format="json")

        item = OrderItem.objects.get(order_id=response.data["id"])
        self.assertEqual(item.variant, self.v1)
        self.assertEqual(item.product, self.v1.product)
        self.assertEqual(item.product_name, self.v1.product.name)
        self.assertEqual(item.variant_name, self.v1.name)
        self.assertEqual(item.sku, self.v1.sku)
        self.assertEqual(item.unit_price, Decimal("10.00"))
        self.assertEqual(item.subtotal, Decimal("20.00"))

    def test_price_changes_do_not_affect_existing_order(self):
        response = self.client.post(self.url, self._payload(), format="json")
        self.v1.selling_price = Decimal("99.00")
        self.v1.save()

        item = OrderItem.objects.get(order_id=response.data["id"])
        self.assertEqual(item.unit_price, Decimal("10.00"))

    def test_initial_status_history_entry_created(self):
        response = self.client.post(self.url, self._payload(), format="json")

        history = OrderStatusHistory.objects.get(order_id=response.data["id"])
        self.assertEqual(history.previous_status, "")
        self.assertEqual(history.new_status, S.PENDING)
        self.assertEqual(history.changed_by, self.user)
        self.assertEqual(len(response.data["status_history"]), 1)

    def test_client_cannot_set_read_only_fields(self):
        payload = self._payload(
            status="DELIVERED",
            total_amount="1.00",
            subtotal="1.00",
            discount_amount="50.00",
            delivery_fee="9.00",
            tax_amount="9.00",
            customer=self.other.pk,
            order_number="HACKED",
        )

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.customer, self.user)
        self.assertEqual(order.status, S.PENDING)
        self.assertEqual(order.total_amount, Decimal("20.00"))
        self.assertEqual(order.discount_amount, Decimal("0.00"))
        self.assertEqual(order.delivery_fee, Decimal("0.00"))
        self.assertNotEqual(order.order_number, "HACKED")

    def test_scheduled_delivery_accepted(self):
        response = self.client.post(
            self.url,
            self._payload(scheduled_delivery="2026-12-01T10:00:00Z"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(Order.objects.get(pk=response.data["id"]).scheduled_delivery)

    # ---------- validation ----------

    def test_missing_order_items_rejected(self):
        response = self.client.post(self.url, {"customer_notes": "x"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("order_items", response.data)

    def test_empty_order_items_rejected(self):
        response = self.client.post(self.url, {"order_items": []}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("order_items", response.data)
        self.assertEqual(Order.objects.count(), 0)

    def test_unknown_variant_rejected(self):
        response = self.client.post(
            self.url,
            {"order_items": [{"variant": "00000000-0000-0000-0000-000000000000", "quantity": "1"}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_variant_rejected(self):
        inactive = make_variant(is_active=False)
        response = self.client.post(
            self.url,
            {"order_items": [{"variant": str(inactive.pk), "quantity": "1.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)

    def test_unavailable_product_rejected_and_rolled_back(self):
        unavailable = make_variant(product=make_product(is_available=False))
        payload = self._payload(
            order_items=[
                {"variant": str(self.v1.pk), "quantity": "1.00"},
                {"variant": str(unavailable.pk), "quantity": "1.00"},
            ]
        )

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(OrderStatusHistory.objects.count(), 0)

    def test_zero_or_negative_quantity_rejected(self):
        for quantity in ["0", "0.00", "-1.00"]:
            response = self.client.post(
                self.url,
                {"order_items": [{"variant": str(self.v1.pk), "quantity": quantity}]},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, quantity)

    def test_missing_quantity_rejected(self):
        response = self.client.post(
            self.url, {"order_items": [{"variant": str(self.v1.pk)}]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ---------- delivery address ----------

    def test_order_with_own_address_stores_snapshot(self):
        # The view's snapshot reads `address.recipient_phone`, but the model
        # field is `recipient_phone_number`, so this currently raises
        # AttributeError (500). Use recipient_phone_number in the serializer.
        self.client.raise_request_exception = False
        address = make_address(self.user)

        response = self.client.post(
            self.url, self._payload(delivery_address=str(address.pk)), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.delivery_address, address)
        snapshot = order.delivery_address_snapshot
        self.assertEqual(snapshot["recipient_name"], "Jane Doe")
        self.assertEqual(snapshot["recipient_phone"], address.recipient_phone_number)
        self.assertEqual(snapshot["district"], "Gasabo")
        self.assertEqual(snapshot["street_address"], "KG 11 Ave")

    def test_snapshot_survives_address_changes(self):
        self.client.raise_request_exception = False  # same recipient_phone bug as above
        address = make_address(self.user)
        response = self.client.post(
            self.url, self._payload(delivery_address=str(address.pk)), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        address.street_address = "Somewhere else"
        address.save()

        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.delivery_address_snapshot["street_address"], "KG 11 Ave")

    def test_cannot_use_another_users_address(self):
        address = make_address(self.other)

        response = self.client.post(
            self.url, self._payload(delivery_address=str(address.pk)), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery_address", response.data)
        self.assertEqual(Order.objects.count(), 0)

    def test_cannot_use_inactive_address(self):
        address = make_address(self.user, is_active=False)

        response = self.client.post(
            self.url, self._payload(delivery_address=str(address.pk)), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery_address", response.data)


# =====================================================
# ORDER READ TESTS
# =====================================================

class OrderReadTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.get(reverse(ORDER_LIST)).status_code, UNAUTHORIZED)

    def test_user_sees_only_own_orders(self):
        mine = create_order(self.user)
        create_order(self.other)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(ORDER_LIST))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ids(response), {str(mine.pk)})

    def test_staff_sees_all_orders(self):
        create_order(self.user)
        create_order(self.other)
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse(ORDER_LIST))

        self.assertEqual(len(results(response)), 2)

    def test_list_newest_first(self):
        older = create_order(self.user)
        newer = create_order(self.user)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(ORDER_LIST))

        self.assertEqual(
            [str(o["id"]) for o in results(response)], [str(newer.pk), str(older.pk)]
        )

    def test_filter_by_status(self):
        pending = create_order(self.user, S.PENDING)
        create_order(self.user, S.DELIVERED)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(ORDER_LIST), {"status": "PENDING"})

        self.assertEqual(ids(response), {str(pending.pk)})

    def test_retrieve_includes_nested_data(self):
        order = create_order(self.user)
        item = create_item(order, quantity="2.00", unit_price="5.00")
        substitution = create_substitution(item)
        OrderStatusHistory.objects.create(
            order=order, new_status=S.PENDING, changed_by=self.user
        )
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(ORDER_DETAIL, args=[order.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["item_count"], 1)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(dec(response.data["items"][0]["subtotal"]), Decimal("10.00"))
        self.assertEqual(len(response.data["status_history"]), 1)
        self.assertEqual(
            [str(s["id"]) for s in response.data["substitutions"]], [str(substitution.pk)]
        )
        self.assertTrue(response.data["customer_name"])
        self.assertNotIn("order_items", response.data)  # write-only

    def test_cannot_retrieve_other_users_order(self):
        order = create_order(self.other)
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(ORDER_DETAIL, args=[order.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_can_retrieve_any_order(self):
        order = create_order(self.user)
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(ORDER_DETAIL, args=[order.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# =====================================================
# ORDER UPDATE / DELETE TESTS
# =====================================================

class OrderUpdateDeleteTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.admin = create_user("admin", is_staff=True)
        self.order = create_order(self.user, customer_notes="Original")
        self.variant = make_variant()
        self.url = reverse(ORDER_DETAIL, args=[self.order.pk])

    def _valid_payload(self, **overrides):
        data = {
            "customer_notes": "Changed",
            "order_items": [{"variant": str(self.variant.pk), "quantity": "1.00"}],
        }
        data.update(overrides)
        return data

    def test_full_payload_update_is_forbidden(self):
        for user in (self.user, self.admin):
            self.client.force_authenticate(user)

            patch = self.client.patch(self.url, self._valid_payload(), format="json")
            put = self.client.put(self.url, self._valid_payload(), format="json")

            self.assertEqual(patch.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(put.status_code, status.HTTP_403_FORBIDDEN)

        self.order.refresh_from_db()
        self.assertEqual(self.order.customer_notes, "Original")

    def test_partial_update_without_items_never_changes_the_order(self):
        # Because validate() always demands "order_items", this is rejected
        # with 400 before perform_update can raise its 403.
        self.client.force_authenticate(self.user)

        response = self.client.patch(self.url, {"customer_notes": "Changed"}, format="json")

        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN],
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.customer_notes, "Original")

    def test_cannot_update_other_users_order(self):
        other = create_user("bob")
        self.client.force_authenticate(other)
        response = self.client.patch(self.url, self._valid_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_is_forbidden_for_everyone(self):
        for user in (self.user, self.admin):
            self.client.force_authenticate(user)
            response = self.client.delete(self.url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())

    def test_unauthenticated_cannot_delete(self):
        response = self.client.delete(self.url)
        self.assertIn(response.status_code, UNAUTHORIZED)


# =====================================================
# ORDER UPDATE-STATUS ACTION TESTS
# =====================================================

class OrderUpdateStatusTests(APITestCase):

    VALID = [
        (S.PENDING, S.CONFIRMED),
        (S.PENDING, S.CANCELLED),
        (S.CONFIRMED, S.PREPARING),
        (S.CONFIRMED, S.CANCELLED),
        (S.PREPARING, S.READY_FOR_DELIVERY),
        (S.PREPARING, S.CANCELLED),
        (S.READY_FOR_DELIVERY, S.OUT_FOR_DELIVERY),
        (S.READY_FOR_DELIVERY, S.CANCELLED),
        (S.OUT_FOR_DELIVERY, S.DELIVERED),
    ]

    INVALID = [
        (S.PENDING, S.PREPARING),
        (S.PENDING, S.DELIVERED),
        (S.PENDING, S.REFUNDED),
        (S.PENDING, S.PENDING),
        (S.CONFIRMED, S.DELIVERED),
        (S.PREPARING, S.OUT_FOR_DELIVERY),
        (S.OUT_FOR_DELIVERY, S.CANCELLED),
        (S.DELIVERED, S.REFUNDED),
        (S.DELIVERED, S.CANCELLED),
        (S.CANCELLED, S.PENDING),
        (S.REFUNDED, S.DELIVERED),
    ]

    def setUp(self):
        self.user = create_user("alice")
        self.admin = create_user("admin", is_staff=True)

    def _post(self, order, new_status, **extra):
        return self.client.post(
            reverse(ORDER_UPDATE_STATUS, args=[order.pk]),
            {"status": new_status, **extra},
            format="json",
        )

    def test_unauthenticated_denied(self):
        order = create_order(self.user)
        self.assertIn(self._post(order, "CONFIRMED").status_code, UNAUTHORIZED)

    def test_customer_cannot_update_status(self):
        order = create_order(self.user)
        self.client.force_authenticate(self.user)

        response = self._post(order, "CONFIRMED")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        order.refresh_from_db()
        self.assertEqual(order.status, S.PENDING)

    def test_all_valid_transitions(self):
        self.client.force_authenticate(self.admin)

        for start, target in self.VALID:
            order = create_order(self.user, start)

            response = self._post(order, target, note=f"{start}->{target}")

            self.assertEqual(response.status_code, status.HTTP_200_OK, f"{start}->{target}")
            self.assertEqual(response.data["status"], target)
            order.refresh_from_db()
            self.assertEqual(order.status, target)

            entry = order.status_history.get()
            self.assertEqual(entry.previous_status, start)
            self.assertEqual(entry.new_status, target)
            self.assertEqual(entry.changed_by, self.admin)
            self.assertEqual(entry.note, f"{start}->{target}")

    def test_all_invalid_transitions_rejected(self):
        self.client.force_authenticate(self.admin)

        for start, target in self.INVALID:
            order = create_order(self.user, start)

            response = self._post(order, target)

            self.assertEqual(
                response.status_code, status.HTTP_400_BAD_REQUEST, f"{start}->{target}"
            )
            order.refresh_from_db()
            self.assertEqual(order.status, start)
            self.assertEqual(order.status_history.count(), 0)

    def test_unknown_status_rejected(self):
        order = create_order(self.user)
        self.client.force_authenticate(self.admin)

        response = self._post(order, "TELEPORTED")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_missing_status_rejected(self):
        order = create_order(self.user)
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(ORDER_UPDATE_STATUS, args=[order.pk]), {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_full_lifecycle(self):
        order = create_order(self.user)
        self.client.force_authenticate(self.admin)

        for step in [
            "CONFIRMED", "PREPARING", "READY_FOR_DELIVERY", "OUT_FOR_DELIVERY", "DELIVERED",
        ]:
            self.assertEqual(self._post(order, step).status_code, status.HTTP_200_OK, step)

        order.refresh_from_db()
        self.assertEqual(order.status, S.DELIVERED)
        self.assertEqual(order.status_history.count(), 5)

    def test_unknown_order_returns_404(self):
        # The action uses Order.objects.get(pk=pk), so an unknown id currently
        # raises DoesNotExist (500). Use get_object_or_404 to fix.
        self.client.raise_request_exception = False
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(ORDER_UPDATE_STATUS, args=[MISSING_UUID]),
            {"status": "CONFIRMED"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# =====================================================
# ORDER CANCEL ACTION TESTS
# =====================================================

class OrderCancelTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)

    def _cancel(self, order, **payload):
        return self.client.post(
            reverse(ORDER_CANCEL, args=[order.pk]), payload, format="json"
        )

    def test_unauthenticated_denied(self):
        order = create_order(self.user)
        self.assertIn(self._cancel(order).status_code, UNAUTHORIZED)

    def test_owner_can_cancel_pending_and_confirmed(self):
        self.client.force_authenticate(self.user)
        for current in [S.PENDING, S.CONFIRMED]:
            order = create_order(self.user, current)

            response = self._cancel(order)

            self.assertEqual(response.status_code, status.HTTP_200_OK, current)
            order.refresh_from_db()
            self.assertEqual(order.status, S.CANCELLED)

    def test_cancel_response_and_history(self):
        order = create_order(self.user)
        self.client.force_authenticate(self.user)

        response = self._cancel(order)

        self.assertTrue(response.data["message"])
        self.assertEqual(response.data["order"]["status"], "CANCELLED")
        entry = order.status_history.get()
        self.assertEqual(entry.previous_status, S.PENDING)
        self.assertEqual(entry.new_status, S.CANCELLED)
        self.assertEqual(entry.changed_by, self.user)
        self.assertEqual(entry.note, "Order cancelled.")

    def test_custom_cancel_note(self):
        order = create_order(self.user)
        self.client.force_authenticate(self.user)

        self._cancel(order, note="Changed my mind")

        self.assertEqual(order.status_history.get().note, "Changed my mind")

    def test_staff_can_cancel_any_order(self):
        order = create_order(self.user)
        self.client.force_authenticate(self.admin)

        response = self._cancel(order)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(order.status_history.get().changed_by, self.admin)

    def test_cannot_cancel_other_users_order(self):
        order = create_order(self.user)
        self.client.force_authenticate(self.other)

        response = self._cancel(order)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        order.refresh_from_db()
        self.assertEqual(order.status, S.PENDING)

    def test_cannot_cancel_after_preparation_starts(self):
        self.client.force_authenticate(self.user)
        for current in [
            S.PREPARING, S.READY_FOR_DELIVERY, S.OUT_FOR_DELIVERY,
            S.DELIVERED, S.CANCELLED, S.REFUNDED,
        ]:
            order = create_order(self.user, current)

            response = self._cancel(order)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, current)
            order.refresh_from_db()
            self.assertEqual(order.status, current)

    def test_cancelling_twice_is_rejected(self):
        order = create_order(self.user)
        self.client.force_authenticate(self.user)

        self.assertEqual(self._cancel(order).status_code, status.HTTP_200_OK)
        self.assertEqual(self._cancel(order).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(order.status_history.count(), 1)

    def test_unknown_order_returns_404(self):
        # Same Order.objects.get(pk=pk) pattern: currently a 500.
        self.client.raise_request_exception = False
        self.client.force_authenticate(self.user)

        response = self.client.post(
            reverse(ORDER_CANCEL, args=[MISSING_UUID]), {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# =====================================================
# ORDER ITEM VIEWSET TESTS
# =====================================================

class OrderItemViewSetTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)
        self.order = create_order(self.user)
        self.item = create_item(self.order, quantity="3.00", unit_price="4.00")
        self.other_item = create_item(create_order(self.other))

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.get(reverse(ITEM_LIST)).status_code, UNAUTHORIZED)

    def test_user_sees_only_own_items(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(ITEM_LIST))
        self.assertEqual(ids(response), {str(self.item.pk)})

    def test_staff_sees_all_items(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(ITEM_LIST))
        self.assertEqual(len(results(response)), 2)

    def test_filter_by_order(self):
        extra = create_item(create_order(self.user))
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(ITEM_LIST), {"order": str(self.order.pk)})

        self.assertEqual(ids(response), {str(self.item.pk)})
        self.assertNotIn(str(extra.pk), ids(response))

    def test_retrieve_item(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(ITEM_DETAIL, args=[self.item.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(dec(response.data["subtotal"]), Decimal("12.00"))
        self.assertEqual(response.data["sku"], self.item.sku)

    def test_cannot_retrieve_other_users_item(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(ITEM_DETAIL, args=[self.other_item.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_only(self):
        self.client.force_authenticate(self.admin)
        url = reverse(ITEM_DETAIL, args=[self.item.pk])

        self.assertEqual(
            self.client.post(reverse(ITEM_LIST), {}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.patch(url, {}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )


# =====================================================
# ORDER STATUS HISTORY VIEWSET TESTS
# =====================================================

class OrderStatusHistoryViewSetTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)
        self.order = create_order(self.user)
        self.first = OrderStatusHistory.objects.create(
            order=self.order, new_status=S.PENDING, changed_by=self.user
        )
        self.second = OrderStatusHistory.objects.create(
            order=self.order, previous_status=S.PENDING, new_status=S.CONFIRMED,
            changed_by=self.admin,
        )
        self.other_entry = OrderStatusHistory.objects.create(
            order=create_order(self.other), new_status=S.PENDING
        )

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.get(reverse(HISTORY_LIST)).status_code, UNAUTHORIZED)

    def test_user_sees_only_own_history_oldest_first(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(HISTORY_LIST))

        self.assertEqual(
            [str(h["id"]) for h in results(response)],
            [str(self.first.pk), str(self.second.pk)],
        )

    def test_staff_sees_all_history(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(HISTORY_LIST))
        self.assertEqual(len(results(response)), 3)

    def test_filter_by_order(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(HISTORY_LIST), {"order": str(self.order.pk)})
        self.assertEqual(ids(response), {str(self.first.pk), str(self.second.pk)})

    def test_changed_by_name(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(HISTORY_DETAIL, args=[self.second.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["changed_by_name"])

    def test_changed_by_name_none_when_unknown(self):
        entry = OrderStatusHistory.objects.create(order=self.order, new_status=S.PREPARING)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(HISTORY_DETAIL, args=[entry.pk]))

        self.assertIsNone(response.data["changed_by_name"])

    def test_cannot_retrieve_other_users_history(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(HISTORY_DETAIL, args=[self.other_entry.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_only(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.post(reverse(HISTORY_LIST), {}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(reverse(HISTORY_DETAIL, args=[self.first.pk])).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )


# =====================================================
# ORDER SUBSTITUTION: CREATE
# =====================================================

class OrderSubstitutionCreateTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.admin = create_user("admin", is_staff=True)
        self.order = create_order(self.user, S.PREPARING)
        self.item = create_item(self.order)
        self.suggested = make_variant()
        self.url = reverse(SUB_LIST)

    def _payload(self, **overrides):
        data = {
            "order_item": str(self.item.pk),
            "requested_variant": str(self.item.variant.pk),
            "suggested_variant": str(self.suggested.pk),
        }
        data.update(overrides)
        return data

    def test_unauthenticated_denied(self):
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_customer_cannot_propose_substitution(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(OrderSubstitution.objects.count(), 0)

    def test_staff_can_propose_substitution(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        substitution = OrderSubstitution.objects.get()
        self.assertEqual(substitution.status, OrderSubstitution.Status.PENDING)
        self.assertEqual(substitution.suggested_variant, self.suggested)
        self.assertEqual(response.data["order_number"], self.order.order_number)
        self.assertEqual(response.data["suggested_variant_name"], self.suggested.name)
        self.assertEqual(response.data["requested_variant_name"], self.item.variant.name)

    def test_status_and_response_in_payload_are_ignored(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            self.url,
            self._payload(status="ACCEPTED", customer_response="Sure"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        substitution = OrderSubstitution.objects.get()
        self.assertEqual(substitution.status, OrderSubstitution.Status.PENDING)
        self.assertEqual(substitution.customer_response, "")

    def test_requested_variant_must_match_item(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            self.url,
            self._payload(requested_variant=str(make_variant().pk)),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("requested_variant", response.data)

    def test_suggested_must_differ_from_requested(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            self.url,
            self._payload(suggested_variant=str(self.item.variant.pk)),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("suggested_variant", response.data)

    def test_inactive_suggested_variant_rejected(self):
        inactive = make_variant(is_active=False)
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            self.url, self._payload(suggested_variant=str(inactive.pk)), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("suggested_variant", response.data)

    def test_rejected_for_finished_orders(self):
        self.client.force_authenticate(self.admin)
        for finished in [S.CANCELLED, S.DELIVERED, S.REFUNDED]:
            order = create_order(self.user, finished)
            item = create_item(order)

            response = self.client.post(
                self.url,
                self._payload(
                    order_item=str(item.pk),
                    requested_variant=str(item.variant.pk),
                ),
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, finished)

        self.assertEqual(OrderSubstitution.objects.count(), 0)

    def test_allowed_for_active_order_states(self):
        self.client.force_authenticate(self.admin)
        for active in [S.PENDING, S.CONFIRMED, S.PREPARING, S.READY_FOR_DELIVERY]:
            order = create_order(self.user, active)
            item = create_item(order)

            response = self.client.post(
                self.url,
                self._payload(
                    order_item=str(item.pk),
                    requested_variant=str(item.variant.pk),
                ),
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_201_CREATED, active)

    def test_required_fields(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ["order_item", "requested_variant", "suggested_variant"]:
            self.assertIn(field, response.data)


# =====================================================
# ORDER SUBSTITUTION: READ / BLOCKED METHODS
# =====================================================

class OrderSubstitutionReadTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)

        self.mine = create_substitution(create_item(create_order(self.user)))
        self.mine_accepted = create_substitution(
            create_item(create_order(self.user)),
            sub_status=OrderSubstitution.Status.ACCEPTED,
        )
        self.theirs = create_substitution(create_item(create_order(self.other)))

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.get(reverse(SUB_LIST)).status_code, UNAUTHORIZED)

    def test_customer_sees_only_own(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(SUB_LIST))
        self.assertEqual(ids(response), {str(self.mine.pk), str(self.mine_accepted.pk)})

    def test_staff_sees_all(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(SUB_LIST))
        self.assertEqual(len(results(response)), 3)

    def test_filter_by_status(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(SUB_LIST), {"status": "ACCEPTED"})
        self.assertEqual(ids(response), {str(self.mine_accepted.pk)})

    def test_cannot_retrieve_other_customers_substitution(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(SUB_DETAIL, args=[self.theirs.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_and_delete_forbidden_for_everyone(self):
        url = reverse(SUB_DETAIL, args=[self.mine.pk])
        for user in (self.user, self.admin):
            self.client.force_authenticate(user)

            self.assertEqual(
                self.client.put(url, {}, format="json").status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                self.client.patch(url, {"status": "ACCEPTED"}, format="json").status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(self.client.delete(url).status_code, status.HTTP_403_FORBIDDEN)

        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, OrderSubstitution.Status.PENDING)


# =====================================================
# ORDER SUBSTITUTION: RESPOND ACTION
# =====================================================

class OrderSubstitutionRespondTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)
        self.order = create_order(self.user, S.PREPARING)
        self.item = create_item(self.order)
        self.substitution = create_substitution(self.item)
        self.url = reverse(SUB_RESPOND, args=[self.substitution.pk])

    def _respond(self, response_value="ACCEPTED", **extra):
        return self.client.post(
            self.url, {"response": response_value, **extra}, format="json"
        )

    def test_unauthenticated_denied(self):
        self.assertIn(self._respond().status_code, UNAUTHORIZED)

    def test_customer_can_accept(self):
        self.client.force_authenticate(self.user)

        response = self._respond("ACCEPTED", customer_response="Sounds good")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.substitution.refresh_from_db()
        self.assertEqual(self.substitution.status, OrderSubstitution.Status.ACCEPTED)
        self.assertEqual(self.substitution.customer_response, "Sounds good")
        self.assertEqual(response.data["status"], "ACCEPTED")

    def test_customer_can_reject(self):
        self.client.force_authenticate(self.user)

        response = self._respond("REJECTED", customer_response="No thanks")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.substitution.refresh_from_db()
        self.assertEqual(self.substitution.status, OrderSubstitution.Status.REJECTED)

    def test_response_message_is_optional(self):
        self.client.force_authenticate(self.user)
        response = self._respond("ACCEPTED")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.substitution.refresh_from_db()
        self.assertEqual(self.substitution.customer_response, "")

    def test_other_customer_cannot_respond(self):
        self.client.force_authenticate(self.other)

        response = self._respond()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.substitution.refresh_from_db()
        self.assertEqual(self.substitution.status, OrderSubstitution.Status.PENDING)

    def test_staff_cannot_respond_on_behalf_of_customer(self):
        self.client.force_authenticate(self.admin)

        response = self._respond()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.substitution.refresh_from_db()
        self.assertEqual(self.substitution.status, OrderSubstitution.Status.PENDING)

    def test_invalid_response_value_rejected(self):
        self.client.force_authenticate(self.user)
        for value in ["MAYBE", "PENDING", "EXPIRED", "accepted", ""]:
            response = self._respond(value)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, value)
            self.assertIn("response", response.data)

        self.substitution.refresh_from_db()
        self.assertEqual(self.substitution.status, OrderSubstitution.Status.PENDING)

    def test_missing_response_value_rejected(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_answer_twice(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self._respond("ACCEPTED").status_code, status.HTTP_200_OK)

        response = self._respond("REJECTED")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.substitution.refresh_from_db()
        self.assertEqual(self.substitution.status, OrderSubstitution.Status.ACCEPTED)

    def test_cannot_answer_expired_substitution(self):
        self.substitution.status = OrderSubstitution.Status.EXPIRED
        self.substitution.save()
        self.client.force_authenticate(self.user)

        response = self._respond("ACCEPTED")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_accepting_does_not_change_the_order_item(self):
        # Documents current behaviour: ACCEPTED only records the answer; it does
        # not swap the variant on the order item or recalculate the totals.
        # Change this test if you add that logic.
        self.client.force_authenticate(self.user)
        original_variant = self.item.variant

        self._respond("ACCEPTED")

        self.item.refresh_from_db()
        self.assertEqual(self.item.variant, original_variant)

    def test_unknown_substitution_returns_404(self):
        # The action uses .get(pk=pk): currently an unknown id gives a 500.
        self.client.raise_request_exception = False
        self.client.force_authenticate(self.user)

        response = self.client.post(
            reverse(SUB_RESPOND, args=[MISSING_UUID]),
            {"response": "ACCEPTED"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)