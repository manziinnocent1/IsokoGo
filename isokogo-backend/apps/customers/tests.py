from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from .models import CustomerAddress, CustomerProfile

User = get_user_model()


# =====================================================
# URL NAMES
# Adjust these if your router basenames are different.
# e.g. router.register("profiles", CustomerProfileViewSet, basename="customer-profile")
#      router.register("addresses", CustomerAddressViewSet, basename="customer-address")
# =====================================================

PROFILE_LIST = "customer-profile-list"
PROFILE_DETAIL = "customer-profile-detail"
ADDRESS_LIST = "customer-address-list"
ADDRESS_DETAIL = "customer-address-detail"


def create_user(username, password="StrongPass123!"):
    """Create a user in a way that works with most custom user models."""
    try:
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password=password,
        )
    except TypeError:
        # Custom user model without a username field
        return User.objects.create_user(
            email=f"{username}@example.com",
            password=password,
        )


def address_payload(**overrides):
    data = {
        "address_name": "Home",
        "recipient_name": "John Doe",
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
    return data


# =====================================================
# MODEL TESTS
# =====================================================

class CustomerModelTests(APITestCase):

    def setUp(self):
        self.user = create_user("modeluser")
        self.profile = CustomerProfile.objects.create(user=self.user)

    def test_profile_str_returns_user(self):
        self.assertEqual(str(self.profile), str(self.user))

    def test_profile_uses_uuid_primary_key(self):
        self.assertEqual(len(str(self.profile.id)), 36)

    def test_profile_is_one_to_one_with_user(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CustomerProfile.objects.create(user=self.user)

    def test_address_str(self):
        address = CustomerAddress.objects.create(
            customer=self.profile, **address_payload()
        )
        self.assertEqual(str(address), "Home - Gasabo")

    def test_address_defaults(self):
        address = CustomerAddress.objects.create(
            customer=self.profile, **address_payload()
        )
        self.assertFalse(address.is_default)
        self.assertTrue(address.is_active)

    def test_deleting_profile_cascades_to_addresses(self):
        CustomerAddress.objects.create(customer=self.profile, **address_payload())
        self.profile.delete()
        self.assertEqual(CustomerAddress.objects.count(), 0)

    def test_deleting_user_cascades_to_profile(self):
        self.user.delete()
        self.assertEqual(CustomerProfile.objects.count(), 0)


# =====================================================
# ADDRESS SERIALIZER TESTS (via API)
# =====================================================

class CustomerAddressValidationTests(APITestCase):

    def setUp(self):
        self.user = create_user("validator")
        self.client.force_authenticate(user=self.user)
        self.url = reverse(ADDRESS_LIST)

    def test_latitude_out_of_range_rejected(self):
        response = self.client.post(
            self.url, address_payload(latitude="95.0000000"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("latitude", response.data)

    def test_longitude_out_of_range_rejected(self):
        response = self.client.post(
            self.url, address_payload(longitude="181.0000000"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("longitude", response.data)

    def test_valid_coordinates_accepted(self):
        response = self.client.post(
            self.url,
            address_payload(latitude="-1.9441000", longitude="30.0619000"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_inactive_address_cannot_be_default(self):
        response = self.client.post(
            self.url,
            address_payload(is_default=True, is_active=False),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_default", response.data)

    def test_cannot_deactivate_existing_default_address(self):
        created = self.client.post(
            self.url, address_payload(is_default=True), format="json"
        )
        detail = reverse(ADDRESS_DETAIL, args=[created.data["id"]])

        response = self.client.patch(detail, {"is_active": False}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_default", response.data)

    def test_required_fields_missing(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for field in [
            "address_name",
            "recipient_name",
            "recipient_phone_number",
            "province",
            "district",
            "sector",
            "cell",
            "street_address",
        ]:
            self.assertIn(field, response.data)


# =====================================================
# CUSTOMER PROFILE VIEWSET TESTS
# =====================================================

class CustomerProfileViewSetTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other_user = create_user("bob")
        self.list_url = reverse(PROFILE_LIST)

    # ---------- authentication ----------

    def test_unauthenticated_list_denied(self):
        response = self.client.get(self.list_url)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_unauthenticated_create_denied(self):
        response = self.client.post(self.list_url, {}, format="json")
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    # ---------- create ----------

    def test_create_profile(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.list_url,
            {"preferred_language": "en", "date_of_birth": "1995-05-20"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        profile = CustomerProfile.objects.get(user=self.user)
        self.assertEqual(profile.preferred_language, "en")
        self.assertEqual(str(profile.date_of_birth), "1995-05-20")

    def test_create_profile_ignores_user_in_payload(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.list_url, {"user": self.other_user.pk}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(CustomerProfile.objects.filter(user=self.user).exists())
        self.assertFalse(CustomerProfile.objects.filter(user=self.other_user).exists())

    def test_cannot_create_second_profile(self):
        CustomerProfile.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.list_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CustomerProfile.objects.filter(user=self.user).count(), 1)

    # ---------- list / retrieve ----------

    def test_list_returns_only_own_profile(self):
        CustomerProfile.objects.create(user=self.user)
        CustomerProfile.objects.create(user=self.other_user)
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if "results" in response.data else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(str(results[0]["user"]), str(self.user.pk))

    def test_retrieve_own_profile_includes_addresses(self):
        profile = CustomerProfile.objects.create(user=self.user)
        CustomerAddress.objects.create(customer=profile, **address_payload())
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse(PROFILE_DETAIL, args=[profile.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["addresses"]), 1)
        self.assertEqual(response.data["addresses"][0]["address_name"], "Home")

    def test_cannot_retrieve_other_users_profile(self):
        other_profile = CustomerProfile.objects.create(user=self.other_user)
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse(PROFILE_DETAIL, args=[other_profile.pk]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ---------- update ----------

    def test_patch_own_profile(self):
        profile = CustomerProfile.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse(PROFILE_DETAIL, args=[profile.pk]),
            {"preferred_language": "rw"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertEqual(profile.preferred_language, "rw")

    def test_cannot_change_profile_owner(self):
        profile = CustomerProfile.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)

        self.client.patch(
            reverse(PROFILE_DETAIL, args=[profile.pk]),
            {"user": self.other_user.pk},
            format="json",
        )

        profile.refresh_from_db()
        self.assertEqual(profile.user, self.user)

    def test_cannot_update_other_users_profile(self):
        other_profile = CustomerProfile.objects.create(user=self.other_user)
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse(PROFILE_DETAIL, args=[other_profile.pk]),
            {"preferred_language": "fr"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        other_profile.refresh_from_db()
        self.assertEqual(other_profile.preferred_language, "")

    # ---------- disallowed methods ----------

    def test_delete_not_allowed(self):
        profile = CustomerProfile.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)

        response = self.client.delete(reverse(PROFILE_DETAIL, args=[profile.pk]))

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(CustomerProfile.objects.filter(pk=profile.pk).exists())


# =====================================================
# CUSTOMER ADDRESS VIEWSET TESTS
# =====================================================

class CustomerAddressViewSetTests(APITestCase):

    def setUp(self):
        self.user = create_user("carol")
        self.other_user = create_user("dave")

        self.profile = CustomerProfile.objects.create(user=self.user)
        self.other_profile = CustomerProfile.objects.create(user=self.other_user)

        self.list_url = reverse(ADDRESS_LIST)
        self.client.force_authenticate(user=self.user)

    def _create_address(self, profile=None, **overrides):
        return CustomerAddress.objects.create(
            customer=profile or self.profile, **address_payload(**overrides)
        )

    def _results(self, response):
        return response.data["results"] if "results" in response.data else response.data

    # ---------- authentication ----------

    def test_unauthenticated_access_denied(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.list_url)

        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    # ---------- create ----------

    def test_create_address(self):
        response = self.client.post(self.list_url, address_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        address = CustomerAddress.objects.get(pk=response.data["id"])
        self.assertEqual(address.customer, self.profile)
        self.assertEqual(address.district, "Gasabo")

    def test_create_address_auto_creates_profile(self):
        new_user = create_user("newbie")
        self.client.force_authenticate(user=new_user)
        self.assertFalse(CustomerProfile.objects.filter(user=new_user).exists())

        response = self.client.post(self.list_url, address_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        profile = CustomerProfile.objects.get(user=new_user)
        self.assertEqual(
            CustomerAddress.objects.get(pk=response.data["id"]).customer, profile
        )

    def test_customer_in_payload_is_ignored(self):
        response = self.client.post(
            self.list_url,
            address_payload(customer=str(self.other_profile.pk)),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            CustomerAddress.objects.get(pk=response.data["id"]).customer,
            self.profile,
        )

    def test_create_default_address_unsets_previous_default(self):
        first = self._create_address(address_name="Home", is_default=True)

        response = self.client.post(
            self.list_url,
            address_payload(address_name="Office", is_default=True),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(CustomerAddress.objects.get(pk=response.data["id"]).is_default)
        self.assertEqual(
            CustomerAddress.objects.filter(customer=self.profile, is_default=True).count(),
            1,
        )

    def test_create_non_default_keeps_existing_default(self):
        first = self._create_address(is_default=True)

        response = self.client.post(
            self.list_url,
            address_payload(address_name="Shop", is_default=False),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        first.refresh_from_db()
        self.assertTrue(first.is_default)

    def test_default_in_one_profile_does_not_affect_another(self):
        other_default = self._create_address(
            profile=self.other_profile, is_default=True
        )

        self.client.post(
            self.list_url, address_payload(is_default=True), format="json"
        )

        other_default.refresh_from_db()
        self.assertTrue(other_default.is_default)

    # ---------- list / retrieve ----------

    def test_list_returns_only_own_addresses(self):
        self._create_address(address_name="Mine")
        self._create_address(profile=self.other_profile, address_name="Theirs")

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["address_name"], "Mine")

    def test_list_ordered_newest_first(self):
        older = self._create_address(address_name="Older")
        newer = self._create_address(address_name="Newer")

        response = self.client.get(self.list_url)

        ids = [str(item["id"]) for item in self._results(response)]
        self.assertEqual(ids, [str(newer.pk), str(older.pk)])

    def test_retrieve_own_address(self):
        address = self._create_address()

        response = self.client.get(reverse(ADDRESS_DETAIL, args=[address.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["id"]), str(address.pk))

    def test_cannot_retrieve_other_users_address(self):
        address = self._create_address(profile=self.other_profile)

        response = self.client.get(reverse(ADDRESS_DETAIL, args=[address.pk]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ---------- update ----------

    def test_patch_own_address(self):
        address = self._create_address()

        response = self.client.patch(
            reverse(ADDRESS_DETAIL, args=[address.pk]),
            {"street_address": "KN 5 Rd"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        address.refresh_from_db()
        self.assertEqual(address.street_address, "KN 5 Rd")

    def test_put_own_address(self):
        address = self._create_address()

        response = self.client.put(
            reverse(ADDRESS_DETAIL, args=[address.pk]),
            address_payload(address_name="Updated", district="Nyarugenge"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        address.refresh_from_db()
        self.assertEqual(address.address_name, "Updated")
        self.assertEqual(address.district, "Nyarugenge")

    def test_update_to_default_unsets_other_defaults(self):
        old_default = self._create_address(address_name="Old", is_default=True)
        address = self._create_address(address_name="New")

        response = self.client.patch(
            reverse(ADDRESS_DETAIL, args=[address.pk]),
            {"is_default": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        old_default.refresh_from_db()
        address.refresh_from_db()
        self.assertFalse(old_default.is_default)
        self.assertTrue(address.is_default)

    def test_update_default_address_keeps_it_default(self):
        address = self._create_address(is_default=True)

        response = self.client.patch(
            reverse(ADDRESS_DETAIL, args=[address.pk]),
            {"is_default": True, "address_name": "Renamed"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        address.refresh_from_db()
        self.assertTrue(address.is_default)
        self.assertEqual(address.address_name, "Renamed")

    def test_cannot_update_other_users_address(self):
        address = self._create_address(profile=self.other_profile)

        response = self.client.patch(
            reverse(ADDRESS_DETAIL, args=[address.pk]),
            {"address_name": "Hacked"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        address.refresh_from_db()
        self.assertEqual(address.address_name, "Home")

    def test_cannot_reassign_address_to_another_customer(self):
        address = self._create_address()

        self.client.patch(
            reverse(ADDRESS_DETAIL, args=[address.pk]),
            {"customer": str(self.other_profile.pk)},
            format="json",
        )

        address.refresh_from_db()
        self.assertEqual(address.customer, self.profile)

    # ---------- delete ----------

    def test_delete_own_address(self):
        address = self._create_address()

        response = self.client.delete(reverse(ADDRESS_DETAIL, args=[address.pk]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CustomerAddress.objects.filter(pk=address.pk).exists())

    def test_cannot_delete_other_users_address(self):
        address = self._create_address(profile=self.other_profile)

        response = self.client.delete(reverse(ADDRESS_DETAIL, args=[address.pk]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(CustomerAddress.objects.filter(pk=address.pk).exists())