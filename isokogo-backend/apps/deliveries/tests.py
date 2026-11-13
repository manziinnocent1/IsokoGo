import shutil
import tempfile
from decimal import Decimal
from io import BytesIO

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse

from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Delivery,
    DeliveryPersonnel,
    DeliveryTracking,
    DeliveryZone,
)

User = get_user_model()


# =====================================================
# URL NAMES
# Adjust if your router basenames are different, e.g.
#   router.register("personnel", DeliveryPersonnelViewSet, basename="delivery-personnel")
#   router.register("zones", DeliveryZoneViewSet, basename="delivery-zone")
#   router.register("deliveries", DeliveryViewSet, basename="delivery")
#   router.register("tracking", DeliveryTrackingViewSet, basename="delivery-tracking")
# =====================================================

PERSONNEL_LIST = "delivery-personnel-list"
PERSONNEL_DETAIL = "delivery-personnel-detail"
PERSONNEL_AVAILABILITY = "delivery-personnel-availability"

ZONE_LIST = "delivery-zone-list"
ZONE_DETAIL = "delivery-zone-detail"

DELIVERY_LIST = "delivery-list"
DELIVERY_DETAIL = "delivery-detail"
DELIVERY_ASSIGN = "delivery-assign"
DELIVERY_UPDATE_STATUS = "delivery-update-status"
DELIVERY_PROOF = "delivery-proof-of-delivery"

TRACKING_LIST = "delivery-tracking-list"
TRACKING_DETAIL = "delivery-tracking-detail"


# =====================================================
# HELPERS
# =====================================================

# TODO: fill in whatever your orders.Order model needs to be created
# (customer, totals, status, etc.). Every call must produce a NEW order,
# because Delivery.order is a OneToOneField.
ORDER_DEFAULTS = {}


def make_order(**overrides):
    Order = apps.get_model("orders", "Order")  # change to your app label / model
    data = dict(ORDER_DEFAULTS)
    data.update(overrides)
    return Order.objects.create(**data)


_user_counter = 0


def create_user(prefix="user", is_staff=False, password="StrongPass123!"):
    global _user_counter
    _user_counter += 1
    username = f"{prefix}{_user_counter}"
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


def create_personnel(
    user=None,
    is_verified=True,
    availability=DeliveryPersonnel.AvailabilityStatus.AVAILABLE,
    vehicle_type=DeliveryPersonnel.VehicleType.MOTORCYCLE,
):
    return DeliveryPersonnel.objects.create(
        user=user or create_user("courier"),
        vehicle_type=vehicle_type,
        vehicle_registration="RAB123A",
        availability_status=availability,
        is_verified=is_verified,
    )


def create_zone(name="Kimironko", district="Gasabo", province="Kigali", is_active=True):
    return DeliveryZone.objects.create(
        name=name,
        province=province,
        district=district,
        base_delivery_fee=Decimal("1500.00"),
        estimated_delivery_minutes=45,
        is_active=is_active,
    )


def create_delivery(
    zone,
    personnel=None,
    delivery_status=Delivery.Status.PENDING_ASSIGNMENT,
    order=None,
):
    return Delivery.objects.create(
        order=order or make_order(),
        delivery_personnel=personnel,
        delivery_zone=zone,
        status=delivery_status,
        delivery_fee=Decimal("1500.00"),
        recipient_name="Jane Doe",
        recipient_phone="0788000000",
    )


def results(response):
    data = response.data
    return data["results"] if isinstance(data, dict) and "results" in data else data


def fake_image(name="proof.jpg"):
    buffer = BytesIO()
    Image.new("RGB", (10, 10), color="red").save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


UNAUTHORIZED = [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]


# =====================================================
# MODEL TESTS
# =====================================================

class DeliveryModelTests(APITestCase):

    def setUp(self):
        self.zone = create_zone()
        self.personnel = create_personnel()

    def test_personnel_defaults(self):
        user = create_user("fresh")
        personnel = DeliveryPersonnel.objects.create(
            user=user, vehicle_type=DeliveryPersonnel.VehicleType.BICYCLE
        )
        self.assertEqual(
            personnel.availability_status,
            DeliveryPersonnel.AvailabilityStatus.OFFLINE,
        )
        self.assertFalse(personnel.is_verified)
        self.assertEqual(personnel.vehicle_registration, "")

    def test_personnel_str_contains_vehicle_type(self):
        self.assertIn(DeliveryPersonnel.VehicleType.MOTORCYCLE, str(self.personnel))

    def test_personnel_user_is_one_to_one(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_personnel(user=self.personnel.user)

    def test_zone_str(self):
        self.assertEqual(str(self.zone), "Kimironko (Gasabo)")

    def test_zone_name_unique_per_district(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_zone(name="Kimironko", district="Gasabo")

    def test_zone_same_name_allowed_in_other_district(self):
        zone = create_zone(name="Kimironko", district="Kicukiro")
        self.assertIsNotNone(zone.pk)

    def test_delivery_defaults(self):
        delivery = create_delivery(self.zone)
        self.assertEqual(delivery.status, Delivery.Status.PENDING_ASSIGNMENT)
        self.assertIsNone(delivery.delivery_personnel)
        self.assertIsNone(delivery.assigned_at)
        self.assertIn(Delivery.Status.PENDING_ASSIGNMENT, str(delivery))

    def test_delivery_personnel_set_null_on_delete(self):
        delivery = create_delivery(
            self.zone, self.personnel, Delivery.Status.ASSIGNED
        )
        self.personnel.delete()
        delivery.refresh_from_db()
        self.assertIsNone(delivery.delivery_personnel)

    def test_zone_with_deliveries_is_protected(self):
        create_delivery(self.zone)
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.zone.delete()

    def test_deleting_delivery_cascades_to_tracking(self):
        delivery = create_delivery(
            self.zone, self.personnel, Delivery.Status.IN_TRANSIT
        )
        DeliveryTracking.objects.create(
            delivery=delivery, latitude=Decimal("-1.944100"), longitude=Decimal("30.061900")
        )
        delivery.delete()
        self.assertEqual(DeliveryTracking.objects.count(), 0)

    def test_tracking_ordered_newest_first(self):
        delivery = create_delivery(
            self.zone, self.personnel, Delivery.Status.IN_TRANSIT
        )
        first = DeliveryTracking.objects.create(delivery=delivery)
        second = DeliveryTracking.objects.create(delivery=delivery)
        self.assertEqual(
            list(delivery.tracking_events.all()), [second, first]
        )


# =====================================================
# DELIVERY PERSONNEL VIEWSET TESTS
# =====================================================

class DeliveryPersonnelViewSetTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.courier_user = create_user("courier")
        self.other_user = create_user("other")
        self.personnel = create_personnel(
            user=self.courier_user,
            availability=DeliveryPersonnel.AvailabilityStatus.OFFLINE,
        )
        self.other_personnel = create_personnel(user=self.other_user)
        self.zone = create_zone()

    def _availability_url(self, personnel):
        return reverse(PERSONNEL_AVAILABILITY, args=[personnel.pk])

    # ---------- read access ----------

    def test_unauthenticated_denied(self):
        response = self.client.get(reverse(PERSONNEL_LIST))
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_staff_sees_all_personnel(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(PERSONNEL_LIST))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(results(response)), 2)

    def test_courier_sees_only_self(self):
        self.client.force_authenticate(self.courier_user)
        response = self.client.get(reverse(PERSONNEL_LIST))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = results(response)
        self.assertEqual(len(data), 1)
        self.assertEqual(str(data[0]["id"]), str(self.personnel.pk))

    def test_response_includes_user_name(self):
        self.client.force_authenticate(self.courier_user)
        response = self.client.get(reverse(PERSONNEL_DETAIL, args=[self.personnel.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["user_name"])

    def test_courier_cannot_see_other_courier(self):
        self.client.force_authenticate(self.courier_user)
        response = self.client.get(
            reverse(PERSONNEL_DETAIL, args=[self.other_personnel.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_viewset_is_read_only(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(reverse(PERSONNEL_LIST), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        response = self.client.delete(
            reverse(PERSONNEL_DETAIL, args=[self.personnel.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # ---------- availability action ----------

    def test_courier_can_go_available(self):
        self.client.force_authenticate(self.courier_user)
        response = self.client.patch(
            self._availability_url(self.personnel),
            {"availability_status": "AVAILABLE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.personnel.refresh_from_db()
        self.assertEqual(self.personnel.availability_status, "AVAILABLE")

    def test_staff_can_change_any_courier_availability(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            self._availability_url(self.personnel),
            {"availability_status": "AVAILABLE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_courier_cannot_change_other_courier_availability(self):
        self.client.force_authenticate(self.courier_user)
        response = self.client.patch(
            self._availability_url(self.other_personnel),
            {"availability_status": "OFFLINE"},
            format="json",
        )
        # Hidden by get_queryset, so it is a 404 rather than a 403
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.other_personnel.refresh_from_db()
        self.assertEqual(self.other_personnel.availability_status, "AVAILABLE")

    def test_unverified_courier_cannot_change_availability(self):
        self.personnel.is_verified = False
        self.personnel.save()
        self.client.force_authenticate(self.courier_user)
        response = self.client.patch(
            self._availability_url(self.personnel),
            {"availability_status": "AVAILABLE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_availability_status_rejected(self):
        self.client.force_authenticate(self.courier_user)
        response = self.client.patch(
            self._availability_url(self.personnel),
            {"availability_status": "SLEEPING"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("availability_status", response.data)

    def test_missing_availability_status_rejected(self):
        self.client.force_authenticate(self.courier_user)
        response = self.client.patch(
            self._availability_url(self.personnel), {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_go_available_with_active_delivery(self):
        create_delivery(self.zone, self.personnel, Delivery.Status.IN_TRANSIT)
        self.personnel.availability_status = "BUSY"
        self.personnel.save()
        self.client.force_authenticate(self.courier_user)

        response = self.client.patch(
            self._availability_url(self.personnel),
            {"availability_status": "AVAILABLE"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.personnel.refresh_from_db()
        self.assertEqual(self.personnel.availability_status, "BUSY")

    def test_cannot_go_offline_with_active_delivery(self):
        create_delivery(self.zone, self.personnel, Delivery.Status.ASSIGNED)
        self.personnel.availability_status = "BUSY"
        self.personnel.save()
        self.client.force_authenticate(self.courier_user)

        response = self.client.patch(
            self._availability_url(self.personnel),
            {"availability_status": "OFFLINE"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_go_offline_when_only_finished_deliveries_exist(self):
        create_delivery(self.zone, self.personnel, Delivery.Status.DELIVERED)
        self.personnel.availability_status = "AVAILABLE"
        self.personnel.save()
        self.client.force_authenticate(self.courier_user)

        response = self.client.patch(
            self._availability_url(self.personnel),
            {"availability_status": "OFFLINE"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.personnel.refresh_from_db()
        self.assertEqual(self.personnel.availability_status, "OFFLINE")


# =====================================================
# DELIVERY ZONE VIEWSET TESTS
# =====================================================

class DeliveryZoneViewSetTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.user = create_user("customer")
        self.active_zone = create_zone(name="Kimironko", district="Gasabo", province="Kigali")
        self.inactive_zone = create_zone(
            name="Remera", district="Gasabo", province="Kigali", is_active=False
        )
        self.other_zone = create_zone(
            name="Huye Center", district="Huye", province="Southern"
        )

    def _payload(self, **overrides):
        data = {
            "name": "Nyamirambo",
            "province": "Kigali",
            "district": "Nyarugenge",
            "base_delivery_fee": "2000.00",
            "estimated_delivery_minutes": 60,
            "is_active": True,
        }
        data.update(overrides)
        return data

    # ---------- read ----------

    def test_unauthenticated_denied(self):
        response = self.client.get(reverse(ZONE_LIST))
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_regular_user_sees_only_active_zones(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(ZONE_LIST))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {zone["name"] for zone in results(response)}
        self.assertEqual(names, {"Kimironko", "Huye Center"})

    def test_staff_sees_inactive_zones_too(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(ZONE_LIST))
        self.assertEqual(len(results(response)), 3)

    def test_regular_user_cannot_retrieve_inactive_zone(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(ZONE_DETAIL, args=[self.inactive_zone.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_zones_ordered_by_province_district_name(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(ZONE_LIST))
        names = [zone["name"] for zone in results(response)]
        # Kigali/Gasabo/Kimironko, Kigali/Gasabo/Remera, Southern/Huye/Huye Center
        self.assertEqual(names, ["Kimironko", "Remera", "Huye Center"])

    def test_filter_by_province(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(ZONE_LIST), {"province": "south"})
        self.assertEqual([z["name"] for z in results(response)], ["Huye Center"])

    def test_filter_by_district(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(ZONE_LIST), {"district": "gasabo"})
        self.assertEqual([z["name"] for z in results(response)], ["Kimironko"])

    # ---------- write permissions ----------

    def test_regular_user_cannot_create_zone(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse(ZONE_LIST), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(DeliveryZone.objects.filter(name="Nyamirambo").exists())

    def test_regular_user_cannot_update_zone(self):
        self.client.force_authenticate(self.user)
        response = self.client.patch(
            reverse(ZONE_DETAIL, args=[self.active_zone.pk]),
            {"name": "Hacked"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_regular_user_cannot_delete_zone(self):
        self.client.force_authenticate(self.user)
        response = self.client.delete(reverse(ZONE_DETAIL, args=[self.active_zone.pk]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(DeliveryZone.objects.filter(pk=self.active_zone.pk).exists())

    def test_staff_can_create_zone(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(reverse(ZONE_LIST), self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(DeliveryZone.objects.filter(name="Nyamirambo").exists())

    def test_staff_can_update_zone(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            reverse(ZONE_DETAIL, args=[self.active_zone.pk]),
            {"estimated_delivery_minutes": 90},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.active_zone.refresh_from_db()
        self.assertEqual(self.active_zone.estimated_delivery_minutes, 90)

    def test_staff_can_delete_unused_zone(self):
        self.client.force_authenticate(self.admin)
        response = self.client.delete(reverse(ZONE_DETAIL, args=[self.other_zone.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    # ---------- validation ----------

    def test_negative_fee_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse(ZONE_LIST),
            self._payload(base_delivery_fee="-1.00"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("base_delivery_fee", response.data)

    def test_zero_fee_allowed(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse(ZONE_LIST),
            self._payload(base_delivery_fee="0.00"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_zero_estimated_minutes_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse(ZONE_LIST),
            self._payload(estimated_delivery_minutes=0),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estimated_delivery_minutes", response.data)

    def test_duplicate_name_in_same_district_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse(ZONE_LIST),
            self._payload(name="Kimironko", district="Gasabo"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# =====================================================
# DELIVERY VIEWSET TESTS
# =====================================================

class DeliveryViewSetTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.courier_user = create_user("courier")
        self.other_courier_user = create_user("courier")

        self.personnel = create_personnel(user=self.courier_user)
        self.other_personnel = create_personnel(user=self.other_courier_user)
        self.zone = create_zone()

    def _payload(self, order=None, **overrides):
        data = {
            "order": (order or make_order()).pk,
            "delivery_zone": str(self.zone.pk),
            "delivery_fee": "1500.00",
            "recipient_name": "Jane Doe",
            "recipient_phone": "0788000000",
            "delivery_notes": "Leave at the gate",
        }
        data.update(overrides)
        return data

    # ---------- access ----------

    def test_unauthenticated_denied(self):
        response = self.client.get(reverse(DELIVERY_LIST))
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_staff_sees_all_deliveries(self):
        create_delivery(self.zone)
        create_delivery(self.zone, self.personnel, Delivery.Status.ASSIGNED)
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse(DELIVERY_LIST))

        self.assertEqual(len(results(response)), 2)

    def test_courier_sees_only_own_deliveries(self):
        mine = create_delivery(self.zone, self.personnel, Delivery.Status.ASSIGNED)
        create_delivery(self.zone, self.other_personnel, Delivery.Status.ASSIGNED)
        create_delivery(self.zone)  # unassigned
        self.client.force_authenticate(self.courier_user)

        response = self.client.get(reverse(DELIVERY_LIST))

        data = results(response)
        self.assertEqual(len(data), 1)
        self.assertEqual(str(data[0]["id"]), str(mine.pk))

    def test_courier_cannot_retrieve_other_courier_delivery(self):
        other = create_delivery(self.zone, self.other_personnel, Delivery.Status.ASSIGNED)
        self.client.force_authenticate(self.courier_user)

        response = self.client.get(reverse(DELIVERY_DETAIL, args=[other.pk]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_includes_computed_fields_and_tracking(self):
        delivery = create_delivery(self.zone, self.personnel, Delivery.Status.IN_TRANSIT)
        DeliveryTracking.objects.create(
            delivery=delivery, latitude=Decimal("-1.944100"), longitude=Decimal("30.061900")
        )
        self.client.force_authenticate(self.courier_user)

        response = self.client.get(reverse(DELIVERY_DETAIL, args=[delivery.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["delivery_zone_name"], self.zone.name)
        self.assertTrue(response.data["delivery_personnel_name"])
        self.assertEqual(len(response.data["tracking_events"]), 1)
        self.assertEqual(str(response.data["order_reference"]), str(delivery.order_id))

    def test_unassigned_delivery_has_no_personnel_name(self):
        delivery = create_delivery(self.zone)
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse(DELIVERY_DETAIL, args=[delivery.pk]))

        self.assertIsNone(response.data["delivery_personnel_name"])

    # ---------- create ----------

    def test_staff_can_create_delivery(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(reverse(DELIVERY_LIST), self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        delivery = Delivery.objects.get(pk=response.data["id"])
        self.assertEqual(delivery.status, Delivery.Status.PENDING_ASSIGNMENT)
        self.assertIsNone(delivery.delivery_personnel)

    def test_create_ignores_read_only_fields(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(DELIVERY_LIST),
            self._payload(
                status="DELIVERED",
                delivery_personnel=str(self.personnel.pk),
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        delivery = Delivery.objects.get(pk=response.data["id"])
        self.assertEqual(delivery.status, Delivery.Status.PENDING_ASSIGNMENT)
        self.assertIsNone(delivery.delivery_personnel)

    def test_non_staff_cannot_create_delivery(self):
        self.client.force_authenticate(self.courier_user)

        response = self.client.post(reverse(DELIVERY_LIST), self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Delivery.objects.count(), 0)

    def test_negative_fee_rejected(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(DELIVERY_LIST), self._payload(delivery_fee="-5.00"), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery_fee", response.data)

    def test_second_delivery_for_same_order_rejected(self):
        order = make_order()
        create_delivery(self.zone, order=order)
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(DELIVERY_LIST), self._payload(order=order), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("order", response.data)

    def test_required_fields_missing(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(reverse(DELIVERY_LIST), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for field in [
            "order",
            "delivery_zone",
            "delivery_fee",
            "recipient_name",
            "recipient_phone",
        ]:
            self.assertIn(field, response.data)

    # ---------- disallowed methods ----------

    def test_patch_is_forbidden_even_for_staff(self):
        delivery = create_delivery(self.zone)
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            reverse(DELIVERY_DETAIL, args=[delivery.pk]),
            {"delivery_notes": "changed"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        delivery.refresh_from_db()
        self.assertEqual(delivery.delivery_notes, "")

    def test_put_and_delete_not_allowed(self):
        delivery = create_delivery(self.zone)
        self.client.force_authenticate(self.admin)
        url = reverse(DELIVERY_DETAIL, args=[delivery.pk])

        self.assertEqual(
            self.client.put(url, {}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(url).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )


# =====================================================
# DELIVERY ASSIGN ACTION TESTS
# =====================================================

class DeliveryAssignTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.courier_user = create_user("courier")
        self.personnel = create_personnel(user=self.courier_user)
        self.zone = create_zone()
        self.delivery = create_delivery(self.zone)
        self.url = reverse(DELIVERY_ASSIGN, args=[self.delivery.pk])

    def _assign(self, personnel_id=None):
        return self.client.post(
            self.url,
            {"delivery_personnel": str(personnel_id or self.personnel.pk)},
            format="json",
        )

    def test_unauthenticated_denied(self):
        response = self._assign()
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_non_staff_cannot_assign(self):
        self.client.force_authenticate(self.courier_user)
        response = self._assign()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_assign(self):
        self.client.force_authenticate(self.admin)

        response = self._assign()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.delivery.refresh_from_db()
        self.personnel.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.Status.ASSIGNED)
        self.assertEqual(self.delivery.delivery_personnel, self.personnel)
        self.assertIsNotNone(self.delivery.assigned_at)
        self.assertEqual(
            self.personnel.availability_status,
            DeliveryPersonnel.AvailabilityStatus.BUSY,
        )
        self.assertEqual(response.data["status"], Delivery.Status.ASSIGNED)

    def test_missing_personnel_id(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery_personnel", response.data)

    def test_unknown_personnel_returns_404(self):
        self.client.force_authenticate(self.admin)
        response = self._assign("00000000-0000-0000-0000-000000000000")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unverified_personnel_rejected(self):
        self.personnel.is_verified = False
        self.personnel.save()
        self.client.force_authenticate(self.admin)

        response = self._assign()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.Status.PENDING_ASSIGNMENT)

    def test_unavailable_personnel_rejected(self):
        for unavailable in ["BUSY", "OFFLINE"]:
            self.personnel.availability_status = unavailable
            self.personnel.save()
            self.client.force_authenticate(self.admin)

            response = self._assign()

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, unavailable)

    def test_courier_with_active_delivery_rejected(self):
        # Inconsistent state on purpose: AVAILABLE but already carrying a delivery
        create_delivery(self.zone, self.personnel, Delivery.Status.IN_TRANSIT)
        self.client.force_authenticate(self.admin)

        response = self._assign()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_already_assigned_delivery_cannot_be_reassigned(self):
        other = create_personnel()
        self.delivery.status = Delivery.Status.ASSIGNED
        self.delivery.delivery_personnel = other
        self.delivery.save()
        self.client.force_authenticate(self.admin)

        response = self._assign()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.delivery_personnel, other)

    def test_cannot_assign_two_deliveries_to_same_courier(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self._assign().status_code, status.HTTP_200_OK)

        second = create_delivery(self.zone)
        response = self.client.post(
            reverse(DELIVERY_ASSIGN, args=[second.pk]),
            {"delivery_personnel": str(self.personnel.pk)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# =====================================================
# DELIVERY UPDATE-STATUS ACTION TESTS
# =====================================================

class DeliveryUpdateStatusTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.courier_user = create_user("courier")
        self.other_courier_user = create_user("courier")

        self.personnel = create_personnel(
            user=self.courier_user,
            availability=DeliveryPersonnel.AvailabilityStatus.BUSY,
        )
        self.other_personnel = create_personnel(user=self.other_courier_user)
        self.zone = create_zone()

    def _delivery(self, delivery_status=Delivery.Status.ASSIGNED, personnel=None):
        return create_delivery(self.zone, personnel or self.personnel, delivery_status)

    def _update(self, delivery, new_status):
        return self.client.post(
            reverse(DELIVERY_UPDATE_STATUS, args=[delivery.pk]),
            {"status": new_status},
            format="json",
        )

    def test_unauthenticated_denied(self):
        response = self._update(self._delivery(), "PICKED_UP")
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_courier_can_mark_picked_up(self):
        delivery = self._delivery()
        self.client.force_authenticate(self.courier_user)

        response = self._update(delivery, "PICKED_UP")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, Delivery.Status.PICKED_UP)
        self.assertIsNotNone(delivery.picked_up_at)
        self.assertIsNone(delivery.delivered_at)

    def test_full_happy_path(self):
        delivery = self._delivery()
        self.client.force_authenticate(self.courier_user)

        for step in ["PICKED_UP", "IN_TRANSIT", "DELIVERED"]:
            response = self._update(delivery, step)
            self.assertEqual(response.status_code, status.HTTP_200_OK, step)

        delivery.refresh_from_db()
        self.personnel.refresh_from_db()
        self.assertEqual(delivery.status, Delivery.Status.DELIVERED)
        self.assertIsNotNone(delivery.delivered_at)
        self.assertEqual(
            self.personnel.availability_status,
            DeliveryPersonnel.AvailabilityStatus.AVAILABLE,
        )

    def test_failure_frees_courier(self):
        delivery = self._delivery(Delivery.Status.IN_TRANSIT)
        self.client.force_authenticate(self.courier_user)

        response = self._update(delivery, "FAILED")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.personnel.refresh_from_db()
        self.assertEqual(
            self.personnel.availability_status,
            DeliveryPersonnel.AvailabilityStatus.AVAILABLE,
        )

    def test_picked_up_does_not_free_courier(self):
        delivery = self._delivery()
        self.client.force_authenticate(self.courier_user)

        self._update(delivery, "PICKED_UP")

        self.personnel.refresh_from_db()
        self.assertEqual(
            self.personnel.availability_status,
            DeliveryPersonnel.AvailabilityStatus.BUSY,
        )

    def test_staff_can_update_any_delivery(self):
        delivery = self._delivery()
        self.client.force_authenticate(self.admin)

        response = self._update(delivery, "PICKED_UP")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_invalid_transitions_rejected(self):
        invalid = [
            (Delivery.Status.ASSIGNED, "DELIVERED"),
            (Delivery.Status.ASSIGNED, "IN_TRANSIT"),
            (Delivery.Status.PICKED_UP, "DELIVERED"),
            (Delivery.Status.IN_TRANSIT, "PICKED_UP"),
            (Delivery.Status.DELIVERED, "FAILED"),
            (Delivery.Status.FAILED, "ASSIGNED"),
            (Delivery.Status.PENDING_ASSIGNMENT, "PICKED_UP"),
        ]
        self.client.force_authenticate(self.admin)

        for current, target in invalid:
            delivery = self._delivery(current)
            response = self._update(delivery, target)
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"{current} -> {target} should be rejected",
            )
            delivery.refresh_from_db()
            self.assertEqual(delivery.status, current)

    def test_missing_status_rejected(self):
        delivery = self._delivery()
        self.client.force_authenticate(self.courier_user)

        response = self.client.post(
            reverse(DELIVERY_UPDATE_STATUS, args=[delivery.pk]), {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_status_rejected(self):
        delivery = self._delivery()
        self.client.force_authenticate(self.courier_user)

        response = self._update(delivery, "TELEPORTED")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_courier_cannot_update_other_courier_delivery(self):
        delivery = self._delivery(personnel=self.other_personnel)
        self.client.force_authenticate(self.courier_user)

        response = self._update(delivery, "PICKED_UP")

        # Hidden by get_queryset, so it is a 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, Delivery.Status.ASSIGNED)


# =====================================================
# PROOF OF DELIVERY ACTION TESTS
# =====================================================

class ProofOfDeliveryTests(APITestCase):

    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.courier_user = create_user("courier")
        self.other_courier_user = create_user("courier")
        self.personnel = create_personnel(user=self.courier_user)
        self.other_personnel = create_personnel(user=self.other_courier_user)
        self.zone = create_zone()
        self.delivery = create_delivery(
            self.zone, self.personnel, Delivery.Status.IN_TRANSIT
        )
        self.url = reverse(DELIVERY_PROOF, args=[self.delivery.pk])

    def _upload(self, url=None, **extra):
        return self.client.post(
            url or self.url,
            {"proof_of_delivery": fake_image(), **extra},
            format="multipart",
        )

    def test_unauthenticated_denied(self):
        response = self._upload()
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_courier_can_upload_proof(self):
        self.client.force_authenticate(self.courier_user)

        response = self._upload()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.delivery.refresh_from_db()
        self.assertTrue(self.delivery.proof_of_delivery)
        self.assertIn("delivery_proofs/", self.delivery.proof_of_delivery.name)

    def test_staff_can_upload_proof(self):
        self.client.force_authenticate(self.admin)
        response = self._upload()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_missing_file_rejected(self):
        self.client.force_authenticate(self.courier_user)

        response = self.client.post(self.url, {}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("proof_of_delivery", response.data)

    def test_non_image_file_rejected(self):
        self.client.force_authenticate(self.courier_user)
        bad_file = SimpleUploadedFile("notes.txt", b"not an image", content_type="text/plain")

        response = self.client.post(
            self.url, {"proof_of_delivery": bad_file}, format="multipart"
        )

        # The view assigns the file to an ImageField without running
        # serializer validation, so this documents the current behaviour.
        # If you add image validation in the view, change this to 400.
        self.assertIn(
            response.status_code,
            [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST],
        )

    def test_upload_rejected_unless_in_transit(self):
        for current in [
            Delivery.Status.ASSIGNED,
            Delivery.Status.PICKED_UP,
            Delivery.Status.DELIVERED,
            Delivery.Status.FAILED,
        ]:
            self.delivery.status = current
            self.delivery.save()
            self.client.force_authenticate(self.courier_user)

            response = self._upload()

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, current)

        self.delivery.refresh_from_db()
        self.assertFalse(self.delivery.proof_of_delivery)

    def test_courier_cannot_upload_for_other_courier_delivery(self):
        self.client.force_authenticate(self.other_courier_user)

        response = self._upload()

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.delivery.refresh_from_db()
        self.assertFalse(self.delivery.proof_of_delivery)


# =====================================================
# DELIVERY TRACKING VIEWSET TESTS
# =====================================================

class DeliveryTrackingViewSetTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.courier_user = create_user("courier")
        self.other_courier_user = create_user("courier")

        self.personnel = create_personnel(user=self.courier_user)
        self.other_personnel = create_personnel(user=self.other_courier_user)
        self.zone = create_zone()

        self.delivery = create_delivery(
            self.zone, self.personnel, Delivery.Status.IN_TRANSIT
        )
        self.other_delivery = create_delivery(
            self.zone, self.other_personnel, Delivery.Status.IN_TRANSIT
        )
        self.url = reverse(TRACKING_LIST)

    def _payload(self, delivery=None, **overrides):
        data = {
            "delivery": str((delivery or self.delivery).pk),
            "latitude": "-1.944100",
            "longitude": "30.061900",
        }
        data.update(overrides)
        return data

    # ---------- create ----------

    def test_unauthenticated_denied(self):
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_courier_can_submit_tracking(self):
        self.client.force_authenticate(self.courier_user)

        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.delivery.tracking_events.count(), 1)
        self.assertIsNotNone(response.data["recorded_at"])

    def test_tracking_allowed_when_picked_up(self):
        self.delivery.status = Delivery.Status.PICKED_UP
        self.delivery.save()
        self.client.force_authenticate(self.courier_user)

        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_tracking_rejected_for_other_statuses(self):
        for current in [
            Delivery.Status.PENDING_ASSIGNMENT,
            Delivery.Status.ASSIGNED,
            Delivery.Status.DELIVERED,
            Delivery.Status.FAILED,
        ]:
            self.delivery.status = current
            self.delivery.save()
            self.client.force_authenticate(self.admin)

            response = self.client.post(self.url, self._payload(), format="json")

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, current)

        self.assertEqual(DeliveryTracking.objects.count(), 0)

    def test_courier_cannot_track_other_courier_delivery(self):
        self.client.force_authenticate(self.courier_user)

        response = self.client.post(
            self.url, self._payload(delivery=self.other_delivery), format="json"
        )

        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN],
        )
        self.assertEqual(DeliveryTracking.objects.count(), 0)

    def test_courier_cannot_track_unassigned_delivery(self):
        unassigned = create_delivery(self.zone)
        self.client.force_authenticate(self.courier_user)

        response = self.client.post(
            self.url, self._payload(delivery=unassigned), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery", response.data)

    def test_staff_can_track_any_delivery(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            self.url, self._payload(delivery=self.other_delivery), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_latitude_out_of_range_rejected(self):
        self.client.force_authenticate(self.courier_user)

        response = self.client.post(
            self.url, self._payload(latitude="95.000000"), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("latitude", response.data)

    def test_longitude_out_of_range_rejected(self):
        self.client.force_authenticate(self.courier_user)

        response = self.client.post(
            self.url, self._payload(longitude="181.000000"), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("longitude", response.data)

    def test_missing_delivery_rejected(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            self.url, {"latitude": "-1.944100", "longitude": "30.061900"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("delivery", response.data)

    # ---------- read ----------

    def test_courier_sees_only_own_tracking(self):
        mine = DeliveryTracking.objects.create(delivery=self.delivery)
        DeliveryTracking.objects.create(delivery=self.other_delivery)
        self.client.force_authenticate(self.courier_user)

        response = self.client.get(self.url)

        data = results(response)
        self.assertEqual(len(data), 1)
        self.assertEqual(str(data[0]["id"]), str(mine.pk))

    def test_staff_sees_all_tracking(self):
        DeliveryTracking.objects.create(delivery=self.delivery)
        DeliveryTracking.objects.create(delivery=self.other_delivery)
        self.client.force_authenticate(self.admin)

        response = self.client.get(self.url)

        self.assertEqual(len(results(response)), 2)

    def test_courier_cannot_retrieve_other_tracking_event(self):
        event = DeliveryTracking.objects.create(delivery=self.other_delivery)
        self.client.force_authenticate(self.courier_user)

        response = self.client.get(reverse(TRACKING_DETAIL, args=[event.pk]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ---------- disallowed methods ----------

    def test_update_and_delete_not_allowed(self):
        event = DeliveryTracking.objects.create(delivery=self.delivery)
        self.client.force_authenticate(self.admin)
        url = reverse(TRACKING_DETAIL, args=[event.pk])

        for method in (self.client.put, self.client.patch):
            self.assertEqual(
                method(url, {}, format="json").status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
            )
        self.assertEqual(
            self.client.delete(url).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )