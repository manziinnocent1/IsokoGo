from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    PurchaseOrder,
    PurchaseOrderItem,
    Stock,
    StockMovement,
    Supplier,
    Warehouse,
)

User = get_user_model()


# =====================================================
# URL NAMES
# These viewsets define `queryset`, so the router derives basenames from the
# model name (lower-cased, no hyphens). If you passed explicit basenames when
# registering, change the constants below to match.
# =====================================================

WAREHOUSE_LIST = "warehouse-list"
WAREHOUSE_DETAIL = "warehouse-detail"

STOCK_LIST = "stock-list"
STOCK_DETAIL = "stock-detail"
STOCK_ADJUST = "stock-adjust"

MOVEMENT_LIST = "stockmovement-list"
MOVEMENT_DETAIL = "stockmovement-detail"

SUPPLIER_LIST = "supplier-list"
SUPPLIER_DETAIL = "supplier-detail"

PO_LIST = "purchaseorder-list"
PO_DETAIL = "purchaseorder-detail"
PO_SUBMIT = "purchaseorder-submit"
PO_RECEIVE = "purchaseorder-receive"
PO_CANCEL = "purchaseorder-cancel"

ITEM_LIST = "purchaseorderitem-list"
ITEM_DETAIL = "purchaseorderitem-detail"

UNAUTHORIZED = [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
MISSING_UUID = "00000000-0000-0000-0000-000000000000"


# =====================================================
# HELPERS
# =====================================================

# TODO: add whatever catalog.ProductVariant needs to be created
# (e.g. a product foreign key, price, etc.). "name" and "sku" are filled in
# automatically because the serializers read them.
VARIANT_DEFAULTS = {}

_counter = {"variant": 0, "user": 0, "po": 0, "wh": 0}


def make_variant(**overrides):
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    _counter["variant"] += 1
    n = _counter["variant"]
    data = {"name": f"Variant {n}", "sku": f"SKU-{n:05d}"}
    data.update(VARIANT_DEFAULTS)
    data.update(overrides)
    return ProductVariant.objects.create(**data)


def create_user(prefix="user", is_staff=False, password="StrongPass123!"):
    _counter["user"] += 1
    username = f"{prefix}{_counter['user']}"
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


def create_warehouse(name=None, is_active=True):
    _counter["wh"] += 1
    return Warehouse.objects.create(
        name=name or f"Warehouse {_counter['wh']}",
        address="KG 1 Ave, Kigali",
        contact_phone="0788000000",
        is_active=is_active,
    )


def create_supplier(name="Acme Supplies", is_active=True):
    return Supplier.objects.create(
        name=name,
        contact_person="Sam Supplier",
        email="sam@acme.test",
        is_active=is_active,
    )


def create_stock(variant=None, warehouse=None, on_hand="0.00", reserved="0.00", reorder="0.00"):
    return Stock.objects.create(
        variant=variant or make_variant(),
        warehouse=warehouse or create_warehouse(),
        quantity_on_hand=Decimal(on_hand),
        quantity_reserved=Decimal(reserved),
        reorder_level=Decimal(reorder),
    )


def create_po(
    supplier=None,
    warehouse=None,
    po_status=PurchaseOrder.Status.DRAFT,
    created_by=None,
):
    _counter["po"] += 1
    return PurchaseOrder.objects.create(
        supplier=supplier or create_supplier(name=f"Supplier {_counter['po']}"),
        warehouse=warehouse or create_warehouse(),
        reference_number=f"PO-{_counter['po']:05d}",
        status=po_status,
        created_by=created_by,
    )


def create_item(po, variant=None, quantity="10.00", unit_cost="2.50"):
    return PurchaseOrderItem.objects.create(
        purchase_order=po,
        variant=variant or make_variant(),
        quantity=Decimal(quantity),
        unit_cost=Decimal(unit_cost),
    )


def results(response):
    data = response.data
    return data["results"] if isinstance(data, dict) and "results" in data else data


def dec(value):
    return Decimal(str(value))


# =====================================================
# MODEL TESTS
# =====================================================

class InventoryModelTests(APITestCase):

    def test_warehouse_str_and_unique_name(self):
        warehouse = create_warehouse(name="Main")
        self.assertEqual(str(warehouse), "Main")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_warehouse(name="Main")

    def test_supplier_str(self):
        self.assertEqual(str(create_supplier(name="Acme")), "Acme")

    def test_stock_quantity_available(self):
        stock = create_stock(on_hand="10.00", reserved="3.50")
        self.assertEqual(stock.quantity_available, Decimal("6.50"))

    def test_stock_needs_reorder(self):
        below = create_stock(on_hand="5.00", reorder="10.00")
        equal = create_stock(on_hand="10.00", reorder="10.00")
        above = create_stock(on_hand="11.00", reorder="10.00")
        self.assertTrue(below.needs_reorder)
        self.assertTrue(equal.needs_reorder)
        self.assertFalse(above.needs_reorder)

    def test_needs_reorder_uses_available_not_on_hand(self):
        stock = create_stock(on_hand="20.00", reserved="15.00", reorder="10.00")
        self.assertTrue(stock.needs_reorder)

    def test_stock_unique_per_variant_and_warehouse(self):
        stock = create_stock()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Stock.objects.create(variant=stock.variant, warehouse=stock.warehouse)

    def test_same_variant_allowed_in_different_warehouses(self):
        variant = make_variant()
        create_stock(variant=variant)
        create_stock(variant=variant)  # create_stock makes a new warehouse
        self.assertEqual(Stock.objects.filter(variant=variant).count(), 2)

    def test_stock_check_constraints(self):
        stock = create_stock(on_hand="10.00")

        for field, value in [
            ("quantity_on_hand", Decimal("-1.00")),
            ("quantity_reserved", Decimal("-1.00")),
            ("quantity_reserved", Decimal("11.00")),  # more than on hand
        ]:
            with self.assertRaises(IntegrityError, msg=f"{field}={value}"):
                with transaction.atomic():
                    Stock.objects.filter(pk=stock.pk).update(**{field: value})

    def test_stock_with_movements_is_protected(self):
        stock = create_stock()
        StockMovement.objects.create(
            stock=stock,
            movement_type=StockMovement.MovementType.PURCHASE,
            quantity=Decimal("1.00"),
        )
        with self.assertRaises(ProtectedError):
            stock.delete()

    def test_movement_ordering_and_str(self):
        stock = create_stock()
        first = StockMovement.objects.create(
            stock=stock, movement_type="PURCHASE", quantity=Decimal("5.00")
        )
        second = StockMovement.objects.create(
            stock=stock, movement_type="DAMAGE", quantity=Decimal("-1.00")
        )
        self.assertEqual(list(stock.movements.all()), [second, first])
        self.assertEqual(str(second), "DAMAGE -1.00")

    def test_purchase_order_defaults(self):
        po = create_po()
        self.assertEqual(po.status, PurchaseOrder.Status.DRAFT)
        self.assertEqual(po.total_amount, Decimal("0.00"))
        self.assertEqual(str(po), po.reference_number)

    def test_purchase_order_reference_unique(self):
        po = create_po()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PurchaseOrder.objects.create(
                    supplier=po.supplier,
                    warehouse=po.warehouse,
                    reference_number=po.reference_number,
                )

    def test_item_subtotal_calculated_on_save(self):
        item = create_item(create_po(), quantity="1.10", unit_cost="3.33")
        self.assertEqual(item.subtotal, Decimal("3.66"))

    def test_item_subtotal_recalculated_on_update(self):
        item = create_item(create_po(), quantity="2.00", unit_cost="5.00")
        item.quantity = Decimal("3.00")
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.subtotal, Decimal("15.00"))

    def test_item_unique_variant_per_purchase_order(self):
        po = create_po()
        item = create_item(po)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_item(po, variant=item.variant)

    def test_items_deleted_with_purchase_order(self):
        po = create_po()
        create_item(po)
        po.delete()
        self.assertEqual(PurchaseOrderItem.objects.count(), 0)


# =====================================================
# WAREHOUSE VIEWSET TESTS
# =====================================================

class WarehouseViewSetTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.user = create_user("viewer")
        self.b = create_warehouse(name="B Warehouse")
        self.a = create_warehouse(name="A Warehouse")
        self.inactive = create_warehouse(name="C Inactive", is_active=False)

    def test_unauthenticated_denied(self):
        response = self.client.get(reverse(WAREHOUSE_LIST))
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_regular_user_can_list_ordered_by_name(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(WAREHOUSE_LIST))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [w["name"] for w in results(response)]
        self.assertEqual(names, ["A Warehouse", "B Warehouse", "C Inactive"])

    def test_regular_user_can_retrieve(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(WAREHOUSE_DETAIL, args=[self.a.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "A Warehouse")

    def test_filter_is_active_true_and_false(self):
        self.client.force_authenticate(self.user)

        active = self.client.get(reverse(WAREHOUSE_LIST), {"is_active": "true"})
        inactive = self.client.get(reverse(WAREHOUSE_LIST), {"is_active": "false"})

        self.assertEqual(len(results(active)), 2)
        self.assertEqual([w["name"] for w in results(inactive)], ["C Inactive"])

    def test_regular_user_cannot_write(self):
        self.client.force_authenticate(self.user)

        create = self.client.post(
            reverse(WAREHOUSE_LIST),
            {"name": "New", "address": "Somewhere"},
            format="json",
        )
        update = self.client.patch(
            reverse(WAREHOUSE_DETAIL, args=[self.a.pk]), {"name": "X"}, format="json"
        )
        delete = self.client.delete(reverse(WAREHOUSE_DETAIL, args=[self.a.pk]))

        self.assertEqual(create.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(update.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Warehouse.objects.filter(pk=self.a.pk, name="A Warehouse").exists())

    def test_staff_can_create_update_delete(self):
        self.client.force_authenticate(self.admin)

        created = self.client.post(
            reverse(WAREHOUSE_LIST),
            {"name": "Fresh", "address": "KN 5 Rd", "contact_phone": "0788111111"},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        pk = created.data["id"]

        updated = self.client.patch(
            reverse(WAREHOUSE_DETAIL, args=[pk]), {"is_active": False}, format="json"
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertFalse(Warehouse.objects.get(pk=pk).is_active)

        deleted = self.client.delete(reverse(WAREHOUSE_DETAIL, args=[pk]))
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)

    def test_duplicate_name_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse(WAREHOUSE_LIST),
            {"name": "A Warehouse", "address": "Elsewhere"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_required_fields(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(reverse(WAREHOUSE_LIST), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)
        self.assertIn("address", response.data)


# =====================================================
# SUPPLIER VIEWSET TESTS
# =====================================================

class SupplierViewSetTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.user = create_user("viewer")
        self.zeta = create_supplier(name="Zeta Ltd")
        self.alpha = create_supplier(name="Alpha Ltd")
        self.dormant = create_supplier(name="Dormant Ltd", is_active=False)

    def test_unauthenticated_denied(self):
        self.assertIn(
            self.client.get(reverse(SUPPLIER_LIST)).status_code, UNAUTHORIZED
        )

    def test_regular_user_can_list_ordered_by_name(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(SUPPLIER_LIST))
        names = [s["name"] for s in results(response)]
        self.assertEqual(names, ["Alpha Ltd", "Dormant Ltd", "Zeta Ltd"])

    def test_filter_is_active(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(SUPPLIER_LIST), {"is_active": "false"})
        self.assertEqual([s["name"] for s in results(response)], ["Dormant Ltd"])

    def test_regular_user_cannot_write(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            reverse(SUPPLIER_LIST), {"name": "Nope"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_create_with_only_name(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse(SUPPLIER_LIST), {"name": "Minimal Co"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Supplier.objects.filter(name="Minimal Co", is_active=True).exists())

    def test_invalid_email_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse(SUPPLIER_LIST),
            {"name": "Bad Email", "email": "not-an-email"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_staff_can_update_and_delete(self):
        self.client.force_authenticate(self.admin)

        updated = self.client.patch(
            reverse(SUPPLIER_DETAIL, args=[self.alpha.pk]),
            {"contact_person": "New Person"},
            format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.alpha.refresh_from_db()
        self.assertEqual(self.alpha.contact_person, "New Person")

        deleted = self.client.delete(reverse(SUPPLIER_DETAIL, args=[self.alpha.pk]))
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)


# =====================================================
# STOCK VIEWSET TESTS
# =====================================================

class StockViewSetTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.user = create_user("viewer")
        self.wh1 = create_warehouse()
        self.wh2 = create_warehouse()
        self.v1 = make_variant()
        self.v2 = make_variant()
        self.v3 = make_variant()

    # ---------- read ----------

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.get(reverse(STOCK_LIST)).status_code, UNAUTHORIZED)

    def test_regular_user_can_read_computed_fields(self):
        stock = create_stock(
            variant=self.v1, warehouse=self.wh1,
            on_hand="10.00", reserved="4.00", reorder="6.00",
        )
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(STOCK_DETAIL, args=[stock.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(dec(response.data["quantity_available"]), Decimal("6.00"))
        self.assertTrue(response.data["needs_reorder"])
        self.assertEqual(response.data["warehouse_name"], self.wh1.name)
        self.assertEqual(response.data["variant_name"], self.v1.name)

    def test_filter_by_warehouse(self):
        create_stock(variant=self.v1, warehouse=self.wh1)
        create_stock(variant=self.v2, warehouse=self.wh2)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(STOCK_LIST), {"warehouse": str(self.wh1.pk)})

        data = results(response)
        self.assertEqual(len(data), 1)
        self.assertEqual(str(data[0]["warehouse"]), str(self.wh1.pk))

    def test_filter_by_variant(self):
        create_stock(variant=self.v1, warehouse=self.wh1)
        create_stock(variant=self.v2, warehouse=self.wh1)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(STOCK_LIST), {"variant": str(self.v2.pk)})

        data = results(response)
        self.assertEqual(len(data), 1)
        self.assertEqual(str(data[0]["variant"]), str(self.v2.pk))

    def test_low_stock_filter(self):
        low = create_stock(variant=self.v1, warehouse=self.wh1, on_hand="5.00", reorder="10.00")
        boundary = create_stock(variant=self.v2, warehouse=self.wh1, on_hand="10.00", reorder="10.00")
        healthy = create_stock(variant=self.v3, warehouse=self.wh1, on_hand="50.00", reorder="10.00")
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(STOCK_LIST), {"low_stock": "true"})

        ids = {str(s["id"]) for s in results(response)}
        self.assertEqual(ids, {str(low.pk), str(boundary.pk)})
        self.assertNotIn(str(healthy.pk), ids)

    def test_low_stock_filter_accounts_for_reserved(self):
        stock = create_stock(
            variant=self.v1, warehouse=self.wh1,
            on_hand="20.00", reserved="15.00", reorder="10.00",
        )
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(STOCK_LIST), {"low_stock": "true"})

        self.assertEqual([str(s["id"]) for s in results(response)], [str(stock.pk)])

    def test_low_stock_false_returns_everything(self):
        create_stock(variant=self.v1, warehouse=self.wh1, on_hand="5.00", reorder="10.00")
        create_stock(variant=self.v2, warehouse=self.wh1, on_hand="50.00", reorder="10.00")
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(STOCK_LIST), {"low_stock": "false"})

        self.assertEqual(len(results(response)), 2)

    # ---------- write ----------

    def test_regular_user_cannot_create(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            reverse(STOCK_LIST),
            {"variant": str(self.v1.pk), "warehouse": str(self.wh1.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_create_stock_record(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(STOCK_LIST),
            {
                "variant": str(self.v1.pk),
                "warehouse": str(self.wh1.pk),
                "reorder_level": "5.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        stock = Stock.objects.get(pk=response.data["id"])
        self.assertEqual(stock.reorder_level, Decimal("5.00"))
        self.assertEqual(stock.quantity_on_hand, Decimal("0.00"))

    def test_create_ignores_quantity_fields(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(STOCK_LIST),
            {
                "variant": str(self.v1.pk),
                "warehouse": str(self.wh1.pk),
                "quantity_on_hand": "999.00",
                "quantity_reserved": "5.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        stock = Stock.objects.get(pk=response.data["id"])
        self.assertEqual(stock.quantity_on_hand, Decimal("0.00"))
        self.assertEqual(stock.quantity_reserved, Decimal("0.00"))

    def test_duplicate_variant_warehouse_rejected(self):
        create_stock(variant=self.v1, warehouse=self.wh1)
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(STOCK_LIST),
            {"variant": str(self.v1.pk), "warehouse": str(self.wh1.pk)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_moving_stock_onto_existing_pair_rejected_on_update(self):
        create_stock(variant=self.v1, warehouse=self.wh1)
        other = create_stock(variant=self.v2, warehouse=self.wh1)
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            reverse(STOCK_DETAIL, args=[other.pk]),
            {"variant": str(self.v1.pk)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_cannot_change_quantity_on_hand(self):
        stock = create_stock(variant=self.v1, warehouse=self.wh1, on_hand="10.00")
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            reverse(STOCK_DETAIL, args=[stock.pk]),
            {"quantity_on_hand": "500.00", "reorder_level": "3.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity_on_hand, Decimal("10.00"))
        self.assertEqual(stock.reorder_level, Decimal("3.00"))

    def test_staff_can_delete_stock_without_movements(self):
        stock = create_stock(variant=self.v1, warehouse=self.wh1)
        self.client.force_authenticate(self.admin)
        response = self.client.delete(reverse(STOCK_DETAIL, args=[stock.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


# =====================================================
# STOCK ADJUST ACTION TESTS
# =====================================================

class StockAdjustTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.user = create_user("viewer")
        self.stock = create_stock(on_hand="10.00", reserved="0.00")
        self.url = reverse(STOCK_ADJUST, args=[self.stock.pk])

    def _adjust(self, **payload):
        data = {"movement_type": "ADJUSTMENT", "quantity": "5.00", "reason": "Count"}
        data.update(payload)
        return self.client.post(self.url, data, format="json")

    def test_unauthenticated_denied(self):
        self.assertIn(self._adjust().status_code, UNAUTHORIZED)

    def test_regular_user_denied(self):
        self.client.force_authenticate(self.user)

        response = self._adjust()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("10.00"))
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_positive_adjustment_adds_stock_and_logs_movement(self):
        self.client.force_authenticate(self.admin)

        response = self._adjust(quantity="5.00", reference="CNT-1", reason="Physical count")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("15.00"))

        movement = StockMovement.objects.get()
        self.assertEqual(movement.stock, self.stock)
        self.assertEqual(movement.movement_type, "ADJUSTMENT")
        self.assertEqual(movement.quantity, Decimal("5.00"))
        self.assertEqual(movement.reference, "CNT-1")
        self.assertEqual(movement.reason, "Physical count")
        self.assertEqual(movement.performed_by, self.admin)

        self.assertEqual(dec(response.data["stock"]["quantity_on_hand"]), Decimal("15.00"))
        self.assertEqual(str(response.data["movement"]["id"]), str(movement.pk))
        self.assertTrue(response.data["message"])

    def test_negative_adjustment_removes_stock(self):
        self.client.force_authenticate(self.admin)

        response = self._adjust(movement_type="DAMAGE", quantity="-4.00")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("6.00"))
        self.assertEqual(StockMovement.objects.get().quantity, Decimal("-4.00"))

    def test_all_listed_movement_types_accepted(self):
        self.client.force_authenticate(self.admin)
        for movement_type in [
            "PURCHASE", "SALE", "RETURN", "ADJUSTMENT", "DAMAGE", "EXPIRY", "TRANSFER",
        ]:
            response = self._adjust(movement_type=movement_type, quantity="1.00")
            self.assertEqual(response.status_code, status.HTTP_200_OK, movement_type)

    def test_invalid_movement_type_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self._adjust(movement_type="MAGIC")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("movement_type", response.data)

    def test_missing_movement_type_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(self.url, {"quantity": "5.00"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zero_quantity_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self._adjust(quantity="0.00")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantity", response.data)

    def test_non_numeric_quantity_rejected(self):
        # Decimal("abc") raises decimal.InvalidOperation, which is neither
        # TypeError nor ValueError, so the view as written lets it escape (500).
        # Catch decimal.InvalidOperation in the view to make this pass.
        self.client.raise_request_exception = False
        self.client.force_authenticate(self.admin)

        response = self._adjust(quantity="abc")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantity", response.data)

    def test_missing_quantity_rejected(self):
        # Same decimal.InvalidOperation issue as above ("None" is not a number).
        self.client.raise_request_exception = False
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            self.url, {"movement_type": "ADJUSTMENT"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reference_too_long_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self._adjust(reference="x" * 101)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reference", response.data)

    def test_cannot_remove_more_than_on_hand(self):
        self.client.force_authenticate(self.admin)

        response = self._adjust(quantity="-11.00")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("10.00"))
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_cannot_reduce_below_reserved(self):
        Stock.objects.filter(pk=self.stock.pk).update(quantity_reserved=Decimal("8.00"))
        self.client.force_authenticate(self.admin)

        response = self._adjust(quantity="-3.00")  # 7 < 8 reserved

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantity", response.data)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("10.00"))
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_can_reduce_exactly_to_reserved(self):
        Stock.objects.filter(pk=self.stock.pk).update(quantity_reserved=Decimal("8.00"))
        self.client.force_authenticate(self.admin)

        response = self._adjust(quantity="-2.00")  # 8 == 8 reserved

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_on_hand, Decimal("8.00"))

    def test_unknown_stock_returns_404(self):
        # The view uses Stock.objects.get(pk=pk) instead of get_object_or_404,
        # so an unknown id currently raises DoesNotExist (500).
        self.client.raise_request_exception = False
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(STOCK_ADJUST, args=[MISSING_UUID]),
            {"movement_type": "ADJUSTMENT", "quantity": "1.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# =====================================================
# STOCK MOVEMENT VIEWSET TESTS
# =====================================================

class StockMovementViewSetTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.user = create_user("viewer")

        self.wh1 = create_warehouse()
        self.wh2 = create_warehouse()
        self.stock1 = create_stock(warehouse=self.wh1, on_hand="10.00")
        self.stock2 = create_stock(warehouse=self.wh2, on_hand="10.00")

        self.m1 = StockMovement.objects.create(
            stock=self.stock1, movement_type="PURCHASE",
            quantity=Decimal("5.00"), performed_by=self.admin,
        )
        self.m2 = StockMovement.objects.create(
            stock=self.stock2, movement_type="DAMAGE",
            quantity=Decimal("-1.00"),
        )

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.get(reverse(MOVEMENT_LIST)).status_code, UNAUTHORIZED)

    def test_regular_user_sees_nothing(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(MOVEMENT_LIST))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(results(response)), 0)

    def test_regular_user_cannot_retrieve(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(MOVEMENT_DETAIL, args=[self.m1.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_sees_all_movements(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(MOVEMENT_LIST))
        self.assertEqual(len(results(response)), 2)

    def test_response_fields(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse(MOVEMENT_DETAIL, args=[self.m1.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["warehouse_name"], self.wh1.name)
        self.assertEqual(response.data["variant_name"], self.stock1.variant.name)
        self.assertTrue(response.data["performed_by_name"])

    def test_performed_by_name_is_none_when_unknown(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(MOVEMENT_DETAIL, args=[self.m2.pk]))
        self.assertIsNone(response.data["performed_by_name"])

    def test_filter_by_stock(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(MOVEMENT_LIST), {"stock": str(self.stock2.pk)})
        self.assertEqual([str(m["id"]) for m in results(response)], [str(self.m2.pk)])

    def test_filter_by_movement_type(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(MOVEMENT_LIST), {"movement_type": "PURCHASE"})
        self.assertEqual([str(m["id"]) for m in results(response)], [str(self.m1.pk)])

    def test_filter_by_warehouse(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(MOVEMENT_LIST), {"warehouse": str(self.wh1.pk)})
        self.assertEqual([str(m["id"]) for m in results(response)], [str(self.m1.pk)])

    def test_viewset_is_read_only(self):
        self.client.force_authenticate(self.admin)
        url = reverse(MOVEMENT_DETAIL, args=[self.m1.pk])

        self.assertEqual(
            self.client.post(reverse(MOVEMENT_LIST), {}, format="json").status_code,
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
# PURCHASE ORDER VIEWSET TESTS
# =====================================================

class PurchaseOrderViewSetTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.user = create_user("viewer")
        self.supplier = create_supplier()
        self.warehouse = create_warehouse()

    def _payload(self, **overrides):
        data = {
            "supplier": str(self.supplier.pk),
            "warehouse": str(self.warehouse.pk),
            "reference_number": "PO-NEW-001",
            "expected_delivery": "2026-12-01",
        }
        data.update(overrides)
        return data

    # ---------- read ----------

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.get(reverse(PO_LIST)).status_code, UNAUTHORIZED)

    def test_regular_user_can_read_with_items_and_names(self):
        po = create_po(self.supplier, self.warehouse)
        item = create_item(po, quantity="2.00", unit_cost="5.00")
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(PO_DETAIL, args=[po.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["supplier_name"], self.supplier.name)
        self.assertEqual(response.data["warehouse_name"], self.warehouse.name)
        self.assertEqual(response.data["item_count"], 1)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["variant_sku"], item.variant.sku)
        self.assertEqual(dec(response.data["items"][0]["subtotal"]), Decimal("10.00"))

    def test_list_newest_first(self):
        old = create_po(self.supplier, self.warehouse)
        new = create_po(self.supplier, self.warehouse)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(PO_LIST))

        ids = [str(p["id"]) for p in results(response)]
        self.assertEqual(ids, [str(new.pk), str(old.pk)])

    # ---------- create ----------

    def test_regular_user_cannot_create(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse(PO_LIST), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_create_draft_purchase_order(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(reverse(PO_LIST), self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        po = PurchaseOrder.objects.get(pk=response.data["id"])
        self.assertEqual(po.status, PurchaseOrder.Status.DRAFT)
        self.assertEqual(po.created_by, self.admin)
        self.assertEqual(po.total_amount, Decimal("0.00"))
        self.assertTrue(response.data["created_by_name"])

    def test_create_ignores_read_only_fields(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(PO_LIST),
            self._payload(status="RECEIVED", total_amount="999.00", created_by=self.user.pk),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        po = PurchaseOrder.objects.get(pk=response.data["id"])
        self.assertEqual(po.status, PurchaseOrder.Status.DRAFT)
        self.assertEqual(po.total_amount, Decimal("0.00"))
        self.assertEqual(po.created_by, self.admin)

    def test_inactive_supplier_rejected(self):
        self.supplier.is_active = False
        self.supplier.save()
        self.client.force_authenticate(self.admin)

        response = self.client.post(reverse(PO_LIST), self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("supplier", response.data)

    def test_inactive_warehouse_rejected(self):
        self.warehouse.is_active = False
        self.warehouse.save()
        self.client.force_authenticate(self.admin)

        response = self.client.post(reverse(PO_LIST), self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("warehouse", response.data)

    def test_duplicate_reference_rejected(self):
        existing = create_po(self.supplier, self.warehouse)
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(PO_LIST),
            self._payload(reference_number=existing.reference_number),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reference_number", response.data)

    def test_required_fields(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(reverse(PO_LIST), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ["supplier", "warehouse", "reference_number"]:
            self.assertIn(field, response.data)

    # ---------- update ----------

    def test_staff_can_patch_draft(self):
        po = create_po(self.supplier, self.warehouse)
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            reverse(PO_DETAIL, args=[po.pk]),
            {"expected_delivery": "2027-01-15"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        po.refresh_from_db()
        self.assertEqual(str(po.expected_delivery), "2027-01-15")

    def test_staff_can_put_draft(self):
        po = create_po(self.supplier, self.warehouse)
        self.client.force_authenticate(self.admin)

        response = self.client.put(
            reverse(PO_DETAIL, args=[po.pk]),
            self._payload(reference_number="PO-RENAMED"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        po.refresh_from_db()
        self.assertEqual(po.reference_number, "PO-RENAMED")

    def test_cannot_edit_non_draft(self):
        self.client.force_authenticate(self.admin)

        for current in [
            PurchaseOrder.Status.SUBMITTED,
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
            PurchaseOrder.Status.RECEIVED,
            PurchaseOrder.Status.CANCELLED,
        ]:
            po = create_po(self.supplier, self.warehouse, current)

            patch = self.client.patch(
                reverse(PO_DETAIL, args=[po.pk]),
                {"expected_delivery": "2027-01-15"},
                format="json",
            )
            put = self.client.put(
                reverse(PO_DETAIL, args=[po.pk]),
                self._payload(reference_number=f"X-{po.reference_number}"),
                format="json",
            )

            self.assertEqual(patch.status_code, status.HTTP_400_BAD_REQUEST, current)
            self.assertEqual(put.status_code, status.HTTP_400_BAD_REQUEST, current)

    def test_cannot_change_status_through_patch(self):
        po = create_po(self.supplier, self.warehouse)
        self.client.force_authenticate(self.admin)

        self.client.patch(
            reverse(PO_DETAIL, args=[po.pk]), {"status": "RECEIVED"}, format="json"
        )

        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.DRAFT)

    def test_regular_user_cannot_update_or_delete(self):
        po = create_po(self.supplier, self.warehouse)
        self.client.force_authenticate(self.user)

        patch = self.client.patch(
            reverse(PO_DETAIL, args=[po.pk]), {"expected_delivery": "2027-01-15"}, format="json"
        )
        delete = self.client.delete(reverse(PO_DETAIL, args=[po.pk]))

        self.assertEqual(patch.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_delete_draft_without_items(self):
        po = create_po(self.supplier, self.warehouse)
        self.client.force_authenticate(self.admin)
        response = self.client.delete(reverse(PO_DETAIL, args=[po.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


# =====================================================
# PURCHASE ORDER WORKFLOW ACTION TESTS (submit / receive / cancel)
# =====================================================

class PurchaseOrderWorkflowTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.user = create_user("viewer")
        self.supplier = create_supplier()
        self.warehouse = create_warehouse()

    def _po(self, po_status=PurchaseOrder.Status.DRAFT, with_items=True):
        po = create_po(self.supplier, self.warehouse, po_status)
        if with_items:
            create_item(po, quantity="10.00", unit_cost="2.50")
        return po

    def _post(self, name, po):
        return self.client.post(reverse(name, args=[po.pk]), {}, format="json")

    # ---------- submit ----------

    def test_unauthenticated_denied(self):
        self.assertIn(self._post(PO_SUBMIT, self._po()).status_code, UNAUTHORIZED)

    def test_regular_user_cannot_run_actions(self):
        self.client.force_authenticate(self.user)
        for name in (PO_SUBMIT, PO_RECEIVE, PO_CANCEL):
            po = self._po(PurchaseOrder.Status.SUBMITTED)
            response = self._post(name, po)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, name)
            po.refresh_from_db()
            self.assertEqual(po.status, PurchaseOrder.Status.SUBMITTED)

    def test_submit_draft(self):
        po = self._po()
        self.client.force_authenticate(self.admin)

        response = self._post(PO_SUBMIT, po)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.SUBMITTED)
        self.assertEqual(response.data["status"], "SUBMITTED")

    def test_submit_without_items_rejected(self):
        po = self._po(with_items=False)
        self.client.force_authenticate(self.admin)

        response = self._post(PO_SUBMIT, po)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.DRAFT)

    def test_submit_non_draft_rejected(self):
        self.client.force_authenticate(self.admin)
        for current in [
            PurchaseOrder.Status.SUBMITTED,
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
            PurchaseOrder.Status.RECEIVED,
            PurchaseOrder.Status.CANCELLED,
        ]:
            po = self._po(current)
            response = self._post(PO_SUBMIT, po)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, current)

    # ---------- receive ----------

    def test_receive_creates_stock_and_movement(self):
        po = self._po(PurchaseOrder.Status.SUBMITTED, with_items=False)
        item = create_item(po, quantity="10.00", unit_cost="2.50")
        self.client.force_authenticate(self.admin)

        response = self._post(PO_RECEIVE, po)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.RECEIVED)

        stock = Stock.objects.get(variant=item.variant, warehouse=self.warehouse)
        self.assertEqual(stock.quantity_on_hand, Decimal("10.00"))

        movement = StockMovement.objects.get(stock=stock)
        self.assertEqual(movement.movement_type, StockMovement.MovementType.PURCHASE)
        self.assertEqual(movement.quantity, Decimal("10.00"))
        self.assertEqual(movement.reference, po.reference_number)
        self.assertEqual(movement.performed_by, self.admin)

        self.assertEqual(response.data["purchase_order"]["status"], "RECEIVED")

    def test_receive_adds_to_existing_stock(self):
        po = self._po(PurchaseOrder.Status.SUBMITTED, with_items=False)
        item = create_item(po, quantity="10.00")
        stock = create_stock(
            variant=item.variant, warehouse=self.warehouse, on_hand="5.00", reorder="2.00"
        )
        self.client.force_authenticate(self.admin)

        response = self._post(PO_RECEIVE, po)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity_on_hand, Decimal("15.00"))
        self.assertEqual(stock.reorder_level, Decimal("2.00"))
        self.assertEqual(Stock.objects.filter(variant=item.variant).count(), 1)

    def test_receive_handles_multiple_items(self):
        po = self._po(PurchaseOrder.Status.SUBMITTED, with_items=False)
        first = create_item(po, quantity="3.00")
        second = create_item(po, quantity="7.50")
        self.client.force_authenticate(self.admin)

        response = self._post(PO_RECEIVE, po)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Stock.objects.get(variant=first.variant).quantity_on_hand, Decimal("3.00")
        )
        self.assertEqual(
            Stock.objects.get(variant=second.variant).quantity_on_hand, Decimal("7.50")
        )
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_receive_partially_received_allowed(self):
        po = self._po(PurchaseOrder.Status.PARTIALLY_RECEIVED)
        self.client.force_authenticate(self.admin)

        response = self._post(PO_RECEIVE, po)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.RECEIVED)

    def test_receive_invalid_statuses_rejected(self):
        self.client.force_authenticate(self.admin)
        for current in [
            PurchaseOrder.Status.DRAFT,
            PurchaseOrder.Status.RECEIVED,
            PurchaseOrder.Status.CANCELLED,
        ]:
            po = self._po(current)
            response = self._post(PO_RECEIVE, po)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, current)

        self.assertEqual(Stock.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_receiving_twice_does_not_double_stock(self):
        po = self._po(PurchaseOrder.Status.SUBMITTED, with_items=False)
        item = create_item(po, quantity="10.00")
        self.client.force_authenticate(self.admin)

        first = self._post(PO_RECEIVE, po)
        second = self._post(PO_RECEIVE, po)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            Stock.objects.get(variant=item.variant).quantity_on_hand, Decimal("10.00")
        )
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_receive_without_items_rejected(self):
        po = self._po(PurchaseOrder.Status.SUBMITTED, with_items=False)
        self.client.force_authenticate(self.admin)

        response = self._post(PO_RECEIVE, po)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.SUBMITTED)

    # ---------- cancel ----------

    def test_cancel_draft_and_submitted(self):
        self.client.force_authenticate(self.admin)
        for current in [PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.SUBMITTED]:
            po = self._po(current)
            response = self._post(PO_CANCEL, po)
            self.assertEqual(response.status_code, status.HTTP_200_OK, current)
            po.refresh_from_db()
            self.assertEqual(po.status, PurchaseOrder.Status.CANCELLED)

    def test_cancel_other_statuses_rejected(self):
        self.client.force_authenticate(self.admin)
        for current in [
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
            PurchaseOrder.Status.RECEIVED,
            PurchaseOrder.Status.CANCELLED,
        ]:
            po = self._po(current)
            response = self._post(PO_CANCEL, po)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, current)
            po.refresh_from_db()
            self.assertEqual(po.status, current)

    def test_cancelled_order_cannot_be_submitted_or_received(self):
        po = self._po(PurchaseOrder.Status.SUBMITTED)
        self.client.force_authenticate(self.admin)
        self._post(PO_CANCEL, po)

        self.assertEqual(self._post(PO_SUBMIT, po).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._post(PO_RECEIVE, po).status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_purchase_order_returns_404(self):
        # Same pattern as stock adjust: the actions use .get(pk=pk), so an
        # unknown id currently raises DoesNotExist (500) instead of a 404.
        self.client.raise_request_exception = False
        self.client.force_authenticate(self.admin)

        for name in (PO_SUBMIT, PO_RECEIVE, PO_CANCEL):
            response = self.client.post(
                reverse(name, args=[MISSING_UUID]), {}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, name)


# =====================================================
# PURCHASE ORDER ITEM VIEWSET TESTS
# =====================================================

class PurchaseOrderItemViewSetTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.user = create_user("viewer")
        self.po = create_po()
        self.v1 = make_variant()
        self.v2 = make_variant()

    def _payload(self, variant=None, **overrides):
        data = {
            "purchase_order": str(self.po.pk),
            "variant": str((variant or self.v1).pk),
            "quantity": "10.00",
            "unit_cost": "2.50",
        }
        data.update(overrides)
        return data

    def _create(self, **kwargs):
        return self.client.post(reverse(ITEM_LIST), self._payload(**kwargs), format="json")

    def _total(self):
        self.po.refresh_from_db()
        return self.po.total_amount

    # ---------- read ----------

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.get(reverse(ITEM_LIST)).status_code, UNAUTHORIZED)

    def test_regular_user_can_read_and_filter(self):
        other_po = create_po()
        mine = create_item(self.po)
        create_item(other_po)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(ITEM_LIST), {"purchase_order": str(self.po.pk)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = results(response)
        self.assertEqual([str(i["id"]) for i in data], [str(mine.pk)])
        self.assertEqual(data[0]["variant_name"], mine.variant.name)
        self.assertEqual(data[0]["variant_sku"], mine.variant.sku)

    # ---------- create ----------

    def test_regular_user_cannot_create(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self._create().status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_create_computes_subtotal_and_total(self):
        self.client.force_authenticate(self.admin)

        response = self._create(quantity="10.00", unit_cost="2.50")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(dec(response.data["subtotal"]), Decimal("25.00"))
        self.assertEqual(self._total(), Decimal("25.00"))

    def test_total_sums_multiple_items(self):
        self.client.force_authenticate(self.admin)

        self._create(variant=self.v1, quantity="10.00", unit_cost="2.50")
        self._create(variant=self.v2, quantity="4.00", unit_cost="3.00")

        self.assertEqual(self._total(), Decimal("37.00"))

    def test_subtotal_in_payload_is_ignored(self):
        self.client.force_authenticate(self.admin)

        response = self._create(subtotal="999.00")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(dec(response.data["subtotal"]), Decimal("25.00"))

    def test_duplicate_variant_in_same_order_rejected(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self._create().status_code, status.HTTP_201_CREATED)

        response = self._create()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.po.items.count(), 1)

    def test_same_variant_allowed_in_different_orders(self):
        other_po = create_po()
        self.client.force_authenticate(self.admin)
        self._create()

        response = self._create(purchase_order=str(other_po.pk))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cannot_add_to_non_draft_order(self):
        self.client.force_authenticate(self.admin)
        for current in [
            PurchaseOrder.Status.SUBMITTED,
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
            PurchaseOrder.Status.RECEIVED,
            PurchaseOrder.Status.CANCELLED,
        ]:
            po = create_po(po_status=current)
            response = self._create(purchase_order=str(po.pk), variant=make_variant())
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, current)
            self.assertEqual(po.items.count(), 0)

    def test_zero_or_negative_quantity_rejected(self):
        self.client.force_authenticate(self.admin)
        for quantity in ["0.00", "-1.00"]:
            response = self._create(quantity=quantity)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, quantity)
            self.assertIn("quantity", response.data)

    def test_negative_unit_cost_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self._create(unit_cost="-0.01")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unit_cost", response.data)

    def test_zero_unit_cost_allowed(self):
        self.client.force_authenticate(self.admin)
        response = self._create(unit_cost="0.00")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(dec(response.data["subtotal"]), Decimal("0.00"))

    def test_required_fields(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(reverse(ITEM_LIST), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ["purchase_order", "variant", "quantity", "unit_cost"]:
            self.assertIn(field, response.data)

    # ---------- update ----------

    def test_update_recalculates_subtotal_and_total(self):
        self.client.force_authenticate(self.admin)
        created = self._create(quantity="10.00", unit_cost="2.50")

        response = self.client.patch(
            reverse(ITEM_DETAIL, args=[created.data["id"]]),
            {"quantity": "20.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(dec(response.data["subtotal"]), Decimal("50.00"))
        self.assertEqual(self._total(), Decimal("50.00"))

    def test_cannot_update_item_of_non_draft_order(self):
        item = create_item(self.po)
        self.po.status = PurchaseOrder.Status.SUBMITTED
        self.po.save()
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            reverse(ITEM_DETAIL, args=[item.pk]), {"quantity": "99.00"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("10.00"))

    def test_regular_user_cannot_update_or_delete(self):
        item = create_item(self.po)
        self.client.force_authenticate(self.user)

        patch = self.client.patch(
            reverse(ITEM_DETAIL, args=[item.pk]), {"quantity": "1.00"}, format="json"
        )
        delete = self.client.delete(reverse(ITEM_DETAIL, args=[item.pk]))

        self.assertEqual(patch.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)

    # ---------- delete ----------

    def test_delete_recalculates_total(self):
        self.client.force_authenticate(self.admin)
        first = self._create(variant=self.v1, quantity="10.00", unit_cost="2.50")
        self._create(variant=self.v2, quantity="4.00", unit_cost="3.00")
        self.assertEqual(self._total(), Decimal("37.00"))

        response = self.client.delete(reverse(ITEM_DETAIL, args=[first.data["id"]]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self._total(), Decimal("12.00"))

    def test_deleting_last_item_resets_total_to_zero(self):
        self.client.force_authenticate(self.admin)
        created = self._create()

        self.client.delete(reverse(ITEM_DETAIL, args=[created.data["id"]]))

        self.assertEqual(self._total(), Decimal("0.00"))

    def test_cannot_delete_item_from_non_draft_order(self):
        item = create_item(self.po)
        self.po.status = PurchaseOrder.Status.SUBMITTED
        self.po.save()
        self.client.force_authenticate(self.admin)

        response = self.client.delete(reverse(ITEM_DETAIL, args=[item.pk]))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(PurchaseOrderItem.objects.filter(pk=item.pk).exists())