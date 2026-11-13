from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from .models import Notification

User = get_user_model()


# =====================================================
# URL NAMES
# The viewset defines `queryset`, so the router's default basename is the
# model name ("notification"). If you registered it with an explicit
# basename, change the constants below.
# =====================================================

LIST = "notification-list"
DETAIL = "notification-detail"
MARK_READ = "notification-mark-as-read"
MARK_UNREAD = "notification-mark-as-unread"
MARK_ALL_READ = "notification-mark-all-as-read"
UNREAD_COUNT = "notification-unread-count"
CLEAR_READ = "notification-clear-read"

UNAUTHORIZED = [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
MISSING_UUID = "00000000-0000-0000-0000-000000000000"

Type = Notification.NotificationType


# =====================================================
# HELPERS
# =====================================================

# TODO: add whatever orders.Order needs to be created besides its customer
# (totals, status, etc.). The create serializer compares
# `related_order.customer_id` with the recipient's id, so `customer` is
# assumed to be a foreign key to the user model. "order_number" is read by
# the notification serializer.
ORDER_DEFAULTS = {}

_counter = {"user": 0, "order": 0}


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


def make_order(customer, **overrides):
    Order = apps.get_model("orders", "Order")  # change to your app label / model
    data = dict(ORDER_DEFAULTS)
    data.update(overrides)
    return Order.objects.create(customer=customer, **data)


def create_notification(recipient, **overrides):
    _counter["order"] += 1
    data = {
        "title": f"Notification {_counter['order']}",
        "message": "Something happened.",
        "notification_type": Type.SYSTEM,
    }
    data.update(overrides)
    return Notification.objects.create(recipient=recipient, **data)


def results(response):
    data = response.data
    return data["results"] if isinstance(data, dict) and "results" in data else data


def ids(response):
    return {str(item["id"]) for item in results(response)}


# =====================================================
# MODEL TESTS
# =====================================================

class NotificationModelTests(APITestCase):

    def setUp(self):
        self.user = create_user("owner")

    def test_defaults(self):
        notification = Notification.objects.create(
            recipient=self.user, title="Hello", message="World"
        )
        self.assertEqual(notification.notification_type, Type.SYSTEM)
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.related_order)
        self.assertIsNotNone(notification.created_at)

    def test_uuid_primary_key(self):
        notification = create_notification(self.user)
        self.assertEqual(len(str(notification.id)), 36)

    def test_str(self):
        notification = create_notification(self.user, title="Order shipped")
        self.assertEqual(str(notification), f"Order shipped -> {self.user.pk}")

    def test_ordering_newest_first(self):
        first = create_notification(self.user)
        second = create_notification(self.user)
        self.assertEqual(list(Notification.objects.all()), [second, first])

    def test_deleted_with_recipient(self):
        create_notification(self.user)
        self.user.delete()
        self.assertEqual(Notification.objects.count(), 0)

    def test_order_deletion_keeps_notification(self):
        order = make_order(self.user)
        notification = create_notification(self.user, related_order=order)

        order.delete()

        notification.refresh_from_db()
        self.assertIsNone(notification.related_order)

    def test_all_expected_types_exist(self):
        self.assertEqual(
            set(Notification.NotificationType.values),
            {
                "ORDER_PLACED", "ORDER_CONFIRMED", "ORDER_CANCELLED", "PAYMENT",
                "DELIVERY_ASSIGNED", "DELIVERY_UPDATE", "PROMOTION", "SYSTEM",
            },
        )


# =====================================================
# LIST / RETRIEVE TESTS
# =====================================================

class NotificationReadTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.get(reverse(LIST)).status_code, UNAUTHORIZED)

    def test_user_sees_only_own_notifications(self):
        mine = create_notification(self.user)
        create_notification(self.other)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(LIST))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ids(response), {str(mine.pk)})

    def test_staff_sees_everyone_s_notifications(self):
        create_notification(self.user)
        create_notification(self.other)
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse(LIST))

        self.assertEqual(len(results(response)), 2)

    def test_list_newest_first(self):
        older = create_notification(self.user)
        newer = create_notification(self.user)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(LIST))

        self.assertEqual(
            [str(n["id"]) for n in results(response)], [str(newer.pk), str(older.pk)]
        )

    def test_filter_by_notification_type(self):
        payment = create_notification(self.user, notification_type=Type.PAYMENT)
        create_notification(self.user, notification_type=Type.PROMOTION)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(LIST), {"notification_type": "PAYMENT"})

        self.assertEqual(ids(response), {str(payment.pk)})

    def test_filter_by_is_read(self):
        unread = create_notification(self.user, is_read=False)
        read = create_notification(self.user, is_read=True)
        self.client.force_authenticate(self.user)

        unread_response = self.client.get(reverse(LIST), {"is_read": "false"})
        read_response = self.client.get(reverse(LIST), {"is_read": "true"})
        upper_response = self.client.get(reverse(LIST), {"is_read": "TRUE"})

        self.assertEqual(ids(unread_response), {str(unread.pk)})
        self.assertEqual(ids(read_response), {str(read.pk)})
        self.assertEqual(ids(upper_response), {str(read.pk)})

    def test_combined_filters(self):
        target = create_notification(
            self.user, notification_type=Type.PAYMENT, is_read=False
        )
        create_notification(self.user, notification_type=Type.PAYMENT, is_read=True)
        create_notification(self.user, notification_type=Type.SYSTEM, is_read=False)
        self.client.force_authenticate(self.user)

        response = self.client.get(
            reverse(LIST), {"notification_type": "PAYMENT", "is_read": "false"}
        )

        self.assertEqual(ids(response), {str(target.pk)})

    def test_retrieve_own_notification(self):
        notification = create_notification(self.user, title="Hi")
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(DETAIL, args=[notification.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Hi")
        self.assertEqual(str(response.data["recipient"]), str(self.user.pk))

    def test_cannot_retrieve_other_users_notification(self):
        notification = create_notification(self.other)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(DETAIL, args=[notification.pk]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_can_retrieve_any_notification(self):
        notification = create_notification(self.other)
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse(DETAIL, args=[notification.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_recipient_name_is_present(self):
        notification = create_notification(self.user)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(DETAIL, args=[notification.pk]))

        self.assertTrue(response.data["recipient_name"])

    def test_order_number_is_none_without_order(self):
        notification = create_notification(self.user)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(DETAIL, args=[notification.pk]))

        self.assertIsNone(response.data["related_order"])
        self.assertIsNone(response.data["order_number"])

    def test_order_number_is_returned_with_order(self):
        order = make_order(self.user)
        notification = create_notification(
            self.user, notification_type=Type.ORDER_PLACED, related_order=order
        )
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(DETAIL, args=[notification.pk]))

        self.assertEqual(str(response.data["related_order"]), str(order.pk))
        self.assertEqual(str(response.data["order_number"]), str(order.order_number))


# =====================================================
# CREATE TESTS
# =====================================================

class NotificationCreateTests(APITestCase):

    def setUp(self):
        self.admin = create_user("admin", is_staff=True)
        self.user = create_user("alice")
        self.other = create_user("bob")

    def _payload(self, **overrides):
        data = {
            "recipient": self.user.pk,
            "title": "Your order shipped",
            "message": "It is on the way.",
            "notification_type": "DELIVERY_UPDATE",
        }
        data.update(overrides)
        return data

    def test_unauthenticated_denied(self):
        response = self.client.post(reverse(LIST), self._payload(), format="json")
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_regular_user_cannot_create(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(reverse(LIST), self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Notification.objects.count(), 0)

    def test_regular_user_cannot_notify_themselves_either(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            reverse(LIST), self._payload(recipient=self.user.pk), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_create_notification(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(reverse(LIST), self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = Notification.objects.get()
        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.title, "Your order shipped")
        self.assertEqual(notification.notification_type, Type.DELIVERY_UPDATE)
        self.assertFalse(notification.is_read)

    def test_type_defaults_to_system(self):
        self.client.force_authenticate(self.admin)
        payload = self._payload()
        del payload["notification_type"]

        response = self.client.post(reverse(LIST), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Notification.objects.get().notification_type, Type.SYSTEM)

    def test_is_read_in_payload_is_ignored(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(LIST), self._payload(is_read=True), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Notification.objects.get().is_read)

    def test_invalid_type_rejected(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(LIST), self._payload(notification_type="GOSSIP"), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("notification_type", response.data)

    def test_required_fields(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(reverse(LIST), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ["recipient", "title", "message"]:
            self.assertIn(field, response.data)

    def test_unknown_recipient_rejected(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(LIST), self._payload(recipient=999999), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("recipient", response.data)

    def test_order_belonging_to_recipient_accepted(self):
        order = make_order(self.user)
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(LIST),
            self._payload(related_order=order.pk, notification_type="ORDER_PLACED"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Notification.objects.get().related_order, order)

    def test_order_belonging_to_someone_else_rejected(self):
        order = make_order(self.other)
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(LIST), self._payload(related_order=order.pk), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("related_order", response.data)
        self.assertEqual(Notification.objects.count(), 0)

    def test_long_title_rejected(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(LIST), self._payload(title="x" * 256), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("title", response.data)


# =====================================================
# UPDATE / DELETE TESTS
# =====================================================

class NotificationUpdateDeleteTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)
        self.notification = create_notification(self.user, title="Original")
        self.url = reverse(DETAIL, args=[self.notification.pk])

    def test_put_and_patch_are_forbidden_for_everyone(self):
        for user in (self.user, self.admin):
            self.client.force_authenticate(user)

            put = self.client.put(
                self.url,
                {"title": "Changed", "message": "m", "notification_type": "SYSTEM"},
                format="json",
            )
            patch = self.client.patch(self.url, {"title": "Changed"}, format="json")

            self.assertEqual(put.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(patch.status_code, status.HTTP_403_FORBIDDEN)

        self.notification.refresh_from_db()
        self.assertEqual(self.notification.title, "Original")

    def test_unauthenticated_cannot_delete(self):
        response = self.client.delete(self.url)
        self.assertIn(response.status_code, UNAUTHORIZED)
        self.assertTrue(Notification.objects.filter(pk=self.notification.pk).exists())

    def test_user_can_delete_own_notification(self):
        self.client.force_authenticate(self.user)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(pk=self.notification.pk).exists())

    def test_user_cannot_delete_other_users_notification(self):
        self.client.force_authenticate(self.other)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Notification.objects.filter(pk=self.notification.pk).exists())

    def test_staff_can_delete_any_notification(self):
        self.client.force_authenticate(self.admin)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


# =====================================================
# MARK AS READ / UNREAD TESTS
# =====================================================

class NotificationMarkReadTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)

    def test_unauthenticated_denied(self):
        notification = create_notification(self.user)
        response = self.client.post(reverse(MARK_READ, args=[notification.pk]))
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_mark_as_read(self):
        notification = create_notification(self.user, is_read=False)
        self.client.force_authenticate(self.user)

        response = self.client.post(reverse(MARK_READ, args=[notification.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertTrue(response.data["message"])
        self.assertTrue(response.data["notification"]["is_read"])
        self.assertEqual(str(response.data["notification"]["id"]), str(notification.pk))

    def test_mark_as_read_is_idempotent(self):
        notification = create_notification(self.user, is_read=True)
        self.client.force_authenticate(self.user)

        response = self.client.post(reverse(MARK_READ, args=[notification.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_mark_as_unread(self):
        notification = create_notification(self.user, is_read=True)
        self.client.force_authenticate(self.user)

        response = self.client.post(reverse(MARK_UNREAD, args=[notification.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)
        self.assertFalse(response.data["notification"]["is_read"])

    def test_cannot_mark_other_users_notification(self):
        notification = create_notification(self.other, is_read=False)
        self.client.force_authenticate(self.user)

        read = self.client.post(reverse(MARK_READ, args=[notification.pk]))
        unread = self.client.post(reverse(MARK_UNREAD, args=[notification.pk]))

        self.assertEqual(read.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(unread.status_code, status.HTTP_404_NOT_FOUND)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_staff_can_mark_any_notification(self):
        notification = create_notification(self.other, is_read=False)
        self.client.force_authenticate(self.admin)

        response = self.client.post(reverse(MARK_READ, args=[notification.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_unknown_notification_returns_404(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse(MARK_READ, args=[MISSING_UUID]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_not_allowed_on_mark_actions(self):
        notification = create_notification(self.user)
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(MARK_READ, args=[notification.pk]))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# =====================================================
# MARK ALL AS READ TESTS
# =====================================================

class NotificationMarkAllAsReadTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)

    def test_unauthenticated_denied(self):
        self.assertIn(
            self.client.post(reverse(MARK_ALL_READ)).status_code, UNAUTHORIZED
        )

    def test_marks_only_own_unread_notifications(self):
        mine_1 = create_notification(self.user, is_read=False)
        mine_2 = create_notification(self.user, is_read=False)
        already_read = create_notification(self.user, is_read=True)
        theirs = create_notification(self.other, is_read=False)
        self.client.force_authenticate(self.user)

        response = self.client.post(reverse(MARK_ALL_READ))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated_count"], 2)
        for notification in (mine_1, mine_2, already_read):
            notification.refresh_from_db()
            self.assertTrue(notification.is_read)
        theirs.refresh_from_db()
        self.assertFalse(theirs.is_read)

    def test_returns_zero_when_nothing_unread(self):
        create_notification(self.user, is_read=True)
        self.client.force_authenticate(self.user)

        response = self.client.post(reverse(MARK_ALL_READ))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated_count"], 0)

    def test_respects_notification_type_filter(self):
        payment = create_notification(self.user, notification_type=Type.PAYMENT)
        promo = create_notification(self.user, notification_type=Type.PROMOTION)
        self.client.force_authenticate(self.user)

        response = self.client.post(
            reverse(MARK_ALL_READ) + "?notification_type=PAYMENT"
        )

        self.assertEqual(response.data["updated_count"], 1)
        payment.refresh_from_db()
        promo.refresh_from_db()
        self.assertTrue(payment.is_read)
        self.assertFalse(promo.is_read)

    def test_staff_only_marks_own_notifications(self):
        # The view builds on get_queryset(), which returns every user's
        # notifications for staff. As written, a staff member pressing
        # "mark all as read" marks EVERYONE's notifications as read, so this
        # test fails until the bulk actions are scoped to request.user.
        mine = create_notification(self.admin, is_read=False)
        theirs = create_notification(self.user, is_read=False)
        self.client.force_authenticate(self.admin)

        self.client.post(reverse(MARK_ALL_READ))

        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertTrue(mine.is_read)
        self.assertFalse(theirs.is_read)


# =====================================================
# UNREAD COUNT TESTS
# =====================================================

class NotificationUnreadCountTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")

    def test_unauthenticated_denied(self):
        self.assertIn(
            self.client.get(reverse(UNREAD_COUNT)).status_code, UNAUTHORIZED
        )

    def test_counts_only_own_unread(self):
        create_notification(self.user, is_read=False)
        create_notification(self.user, is_read=False)
        create_notification(self.user, is_read=True)
        create_notification(self.other, is_read=False)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(UNREAD_COUNT))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unread_count"], 2)

    def test_zero_when_no_notifications(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(UNREAD_COUNT))
        self.assertEqual(response.data["unread_count"], 0)

    def test_respects_notification_type_filter(self):
        create_notification(self.user, notification_type=Type.PAYMENT)
        create_notification(self.user, notification_type=Type.PROMOTION)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(UNREAD_COUNT), {"notification_type": "PAYMENT"})

        self.assertEqual(response.data["unread_count"], 1)

    def test_count_drops_after_marking_as_read(self):
        notification = create_notification(self.user, is_read=False)
        self.client.force_authenticate(self.user)

        self.client.post(reverse(MARK_READ, args=[notification.pk]))
        response = self.client.get(reverse(UNREAD_COUNT))

        self.assertEqual(response.data["unread_count"], 0)

    def test_post_not_allowed(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse(UNREAD_COUNT))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# =====================================================
# CLEAR READ TESTS
# =====================================================

class NotificationClearReadTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.delete(reverse(CLEAR_READ)).status_code, UNAUTHORIZED)

    def test_deletes_only_own_read_notifications(self):
        read_1 = create_notification(self.user, is_read=True)
        read_2 = create_notification(self.user, is_read=True)
        unread = create_notification(self.user, is_read=False)
        theirs_read = create_notification(self.other, is_read=True)
        self.client.force_authenticate(self.user)

        response = self.client.delete(reverse(CLEAR_READ))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted_count"], 2)
        self.assertFalse(Notification.objects.filter(pk__in=[read_1.pk, read_2.pk]).exists())
        self.assertTrue(Notification.objects.filter(pk=unread.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=theirs_read.pk).exists())

    def test_returns_zero_when_nothing_to_clear(self):
        create_notification(self.user, is_read=False)
        self.client.force_authenticate(self.user)

        response = self.client.delete(reverse(CLEAR_READ))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted_count"], 0)
        self.assertEqual(Notification.objects.count(), 1)

    def test_respects_notification_type_filter(self):
        payment = create_notification(
            self.user, notification_type=Type.PAYMENT, is_read=True
        )
        promo = create_notification(
            self.user, notification_type=Type.PROMOTION, is_read=True
        )
        self.client.force_authenticate(self.user)

        response = self.client.delete(reverse(CLEAR_READ) + "?notification_type=PAYMENT")

        self.assertEqual(response.data["deleted_count"], 1)
        self.assertFalse(Notification.objects.filter(pk=payment.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=promo.pk).exists())

    def test_get_not_allowed(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse(CLEAR_READ))
        # "clear-read" is only routed for DELETE; a GET must never delete anything
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_staff_only_clears_own_notifications(self):
        # Same scoping problem as mark_all_as_read: for staff the queryset
        # contains every user's notifications, so as written this deletes
        # all read notifications in the system. This test fails until the
        # action is scoped to request.user.
        mine = create_notification(self.admin, is_read=True)
        theirs = create_notification(self.user, is_read=True)
        self.client.force_authenticate(self.admin)

        self.client.delete(reverse(CLEAR_READ))

        self.assertFalse(Notification.objects.filter(pk=mine.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=theirs.pk).exists())