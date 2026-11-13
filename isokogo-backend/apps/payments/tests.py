import re
from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from .models import Payment, PaymentTransaction

User = get_user_model()


# =====================================================
# URL NAMES
# These viewsets define `queryset`, so the router derives basenames from the
# model name (lower-cased, no hyphens). If you passed explicit basenames when
# registering, change the constants below to match.
# =====================================================

PAYMENT_LIST = "payment-list"
PAYMENT_DETAIL = "payment-detail"
PAYMENT_CANCEL = "payment-cancel"
PAYMENT_UPDATE_STATUS = "payment-update-status"

TX_LIST = "paymenttransaction-list"
TX_DETAIL = "paymenttransaction-detail"

UNAUTHORIZED = [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
MISSING_UUID = "00000000-0000-0000-0000-000000000000"

P = Payment.Status
T = PaymentTransaction.Status


# =====================================================
# HELPERS
# =====================================================

_c = {"user": 0, "order": 0, "payment": 0}


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


def create_order(customer, total="10000.00", order_status="PENDING"):
    Order = apps.get_model("orders", "Order")  # change to your app label if needed
    _c["order"] += 1
    return Order.objects.create(
        order_number=f"ORD-PAYTEST-{_c['order']:05d}",
        customer=customer,
        status=order_status,
        total_amount=Decimal(total),
    )


def create_payment(
    order,
    customer=None,
    amount=None,
    payment_status=P.PENDING,
    provider=Payment.Provider.MTN_MOMO,
    method=Payment.PaymentMethod.MOBILE_MONEY,
    **overrides,
):
    _c["payment"] += 1
    data = {
        "order": order,
        "customer": customer or order.customer,
        "payment_reference": f"PAY-TEST-{_c['payment']:05d}",
        "provider": provider,
        "payment_method": method,
        "amount": Decimal(amount) if amount is not None else order.total_amount,
        "status": payment_status,
    }
    data.update(overrides)
    return Payment.objects.create(**data)


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

class PaymentModelTests(APITestCase):

    def setUp(self):
        self.user = create_user("owner")
        self.order = create_order(self.user)

    def test_payment_defaults_and_str(self):
        payment = Payment.objects.create(
            order=self.order,
            customer=self.user,
            payment_reference="PAY-X1",
            payment_method=Payment.PaymentMethod.CASH,
            amount=Decimal("100.00"),
        )
        self.assertEqual(payment.status, P.PENDING)
        self.assertEqual(payment.provider, Payment.Provider.OTHER)
        self.assertEqual(payment.currency, "RWF")
        self.assertIsNone(payment.transaction_id)
        self.assertIsNone(payment.paid_at)
        self.assertEqual(str(payment), "PAY-X1 - pending")

    def test_payment_reference_unique(self):
        payment = create_payment(self.order)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_payment(
                    self.order, payment_reference=payment.payment_reference
                )

    def test_payments_newest_first(self):
        first = create_payment(self.order)
        second = create_payment(self.order)
        self.assertEqual(list(Payment.objects.all()), [second, first])

    def test_order_with_payments_is_protected(self):
        create_payment(self.order)
        with self.assertRaises(ProtectedError):
            self.order.delete()

    def test_customer_with_payments_is_protected(self):
        other = create_user("payer")
        order = create_order(other)
        create_payment(order)
        with self.assertRaises(ProtectedError):
            other.delete()

    def test_transaction_defaults_and_str(self):
        payment = create_payment(self.order, payment_reference="PAY-X2")
        tx = PaymentTransaction.objects.create(payment=payment)
        self.assertEqual(tx.status, T.INITIATED)
        self.assertEqual(tx.request_payload, {})
        self.assertEqual(tx.response_payload, {})
        self.assertIsNone(tx.provider_transaction_id)
        self.assertEqual(str(tx), "PAY-X2 - initiated")

    def test_transactions_newest_first(self):
        payment = create_payment(self.order)
        first = PaymentTransaction.objects.create(payment=payment)
        second = PaymentTransaction.objects.create(payment=payment)
        self.assertEqual(list(payment.transactions.all()), [second, first])

    def test_deleting_payment_cascades_to_transactions(self):
        # Payment rows are protected by the API, but at model level the
        # transactions cascade with their payment.
        payment = create_payment(self.order)
        PaymentTransaction.objects.create(payment=payment)
        payment.delete()
        self.assertEqual(PaymentTransaction.objects.count(), 0)


# =====================================================
# PAYMENT CREATE TESTS
# =====================================================

class PaymentCreateTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)
        self.order = create_order(self.user, total="10000.00")
        self.url = reverse(PAYMENT_LIST)
        self.client.force_authenticate(self.user)

    def _payload(self, **overrides):
        data = {
            "order": str(self.order.pk),
            "provider": "mtn_momo",
            "payment_method": "mobile_money",
        }
        data.update(overrides)
        return data

    def test_unauthenticated_denied(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertIn(response.status_code, UNAUTHORIZED)

    def test_customer_can_initiate_payment(self):
        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment = Payment.objects.get(pk=response.data["id"])
        self.assertEqual(payment.customer, self.user)
        self.assertEqual(payment.order, self.order)
        self.assertEqual(payment.status, P.PENDING)
        self.assertEqual(payment.provider, "mtn_momo")
        self.assertEqual(payment.payment_method, "mobile_money")
        self.assertEqual(payment.currency, "RWF")
        self.assertEqual(payment.amount, Decimal("10000.00"))
        self.assertRegex(payment.payment_reference, r"^PAY-[A-Z0-9]{16}$")
        self.assertEqual(response.data["order_number"], self.order.order_number)
        self.assertTrue(response.data["customer_name"])

    def test_initial_transaction_is_logged(self):
        response = self.client.post(self.url, self._payload(), format="json")

        payment = Payment.objects.get(pk=response.data["id"])
        tx = payment.transactions.get()
        self.assertEqual(tx.status, T.INITIATED)
        self.assertEqual(tx.request_payload["provider"], "mtn_momo")
        self.assertEqual(tx.request_payload["payment_method"], "mobile_money")
        self.assertEqual(tx.request_payload["amount"], "10000.00")
        self.assertEqual(tx.request_payload["currency"], "RWF")
        self.assertEqual(len(response.data["transactions"]), 1)

    def test_client_cannot_set_read_only_fields(self):
        payload = self._payload(
            amount="1.00",
            status="successful",
            customer=self.other.pk,
            payment_reference="HACKED",
            transaction_id="FAKE-TX",
            paid_at="2026-01-01T00:00:00Z",
        )

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment = Payment.objects.get(pk=response.data["id"])
        self.assertEqual(payment.amount, Decimal("10000.00"))
        self.assertEqual(payment.status, P.PENDING)
        self.assertEqual(payment.customer, self.user)
        self.assertNotEqual(payment.payment_reference, "HACKED")
        self.assertIsNone(payment.transaction_id)
        self.assertIsNone(payment.paid_at)

    def test_provider_defaults_to_other(self):
        payload = self._payload()
        del payload["provider"]

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Payment.objects.get(pk=response.data["id"]).provider, Payment.Provider.OTHER
        )

    def test_custom_currency_accepted(self):
        response = self.client.post(
            self.url, self._payload(currency="USD"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Payment.objects.get(pk=response.data["id"]).currency, "USD")

    # ---------- outstanding amount ----------

    def test_amount_is_remaining_balance_after_partial_payment(self):
        create_payment(self.order, amount="4000.00", payment_status=P.SUCCESSFUL)

        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(dec(response.data["amount"]), Decimal("6000.00"))

    def test_only_successful_payments_reduce_outstanding(self):
        create_payment(self.order, amount="4000.00", payment_status=P.PENDING)
        create_payment(self.order, amount="3000.00", payment_status=P.FAILED)
        create_payment(self.order, amount="2000.00", payment_status=P.CANCELLED)

        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(dec(response.data["amount"]), Decimal("10000.00"))

    def test_fully_paid_order_rejected(self):
        create_payment(self.order, amount="10000.00", payment_status=P.SUCCESSFUL)

        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("order", response.data)
        self.assertEqual(Payment.objects.count(), 1)

    # ---------- validation ----------

    def test_cannot_pay_for_another_users_order(self):
        order = create_order(self.other)

        response = self.client.post(
            self.url, self._payload(order=str(order.pk)), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("order", response.data)
        self.assertEqual(Payment.objects.count(), 0)

    def test_cancelled_and_refunded_orders_rejected(self):
        for blocked in ["CANCELLED", "REFUNDED"]:
            order = create_order(self.user, order_status=blocked)

            response = self.client.post(
                self.url, self._payload(order=str(order.pk)), format="json"
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, blocked)
            self.assertIn("order", response.data)

        self.assertEqual(Payment.objects.count(), 0)

    def test_zero_total_order_rejected(self):
        order = create_order(self.user, total="0.00")

        response = self.client.post(
            self.url, self._payload(order=str(order.pk)), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("order", response.data)

    def test_delivered_order_can_still_be_paid(self):
        order = create_order(self.user, order_status="DELIVERED")
        response = self.client.post(
            self.url, self._payload(order=str(order.pk)), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_unknown_order_rejected(self):
        response = self.client.post(
            self.url, self._payload(order=MISSING_UUID), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("order", response.data)

    def test_invalid_provider_rejected(self):
        response = self.client.post(
            self.url, self._payload(provider="bitcoin"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("provider", response.data)

    def test_invalid_payment_method_rejected(self):
        response = self.client.post(
            self.url, self._payload(payment_method="barter"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("payment_method", response.data)

    def test_overlong_currency_rejected(self):
        response = self.client.post(
            self.url, self._payload(currency="RWFX"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("currency", response.data)

    def test_required_fields(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("order", response.data)
        self.assertIn("payment_method", response.data)

    # ---------- staff ----------

    def test_staff_can_initiate_payment_for_any_order(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_staff_created_payment_belongs_to_the_orders_customer(self):
        # create() always uses request.user as the customer, so a payment that
        # staff initiate for a customer's order ends up owned by the staff
        # user and is invisible to the customer. This test fails until create()
        # uses order.customer instead.
        self.client.force_authenticate(self.admin)

        response = self.client.post(self.url, self._payload(), format="json")

        payment = Payment.objects.get(pk=response.data["id"])
        self.assertEqual(payment.customer, self.user)


# =====================================================
# PAYMENT READ TESTS
# =====================================================

class PaymentReadTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)
        self.order = create_order(self.user)
        self.other_order = create_order(self.other)

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.get(reverse(PAYMENT_LIST)).status_code, UNAUTHORIZED)

    def test_customer_sees_only_own_payments(self):
        mine = create_payment(self.order)
        create_payment(self.other_order)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(PAYMENT_LIST))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ids(response), {str(mine.pk)})

    def test_staff_sees_all_payments(self):
        create_payment(self.order)
        create_payment(self.other_order)
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse(PAYMENT_LIST))

        self.assertEqual(len(results(response)), 2)

    def test_list_newest_first(self):
        older = create_payment(self.order)
        newer = create_payment(self.order)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(PAYMENT_LIST))

        self.assertEqual(
            [str(p["id"]) for p in results(response)], [str(newer.pk), str(older.pk)]
        )

    def test_filter_by_status(self):
        pending = create_payment(self.order, payment_status=P.PENDING)
        create_payment(self.order, payment_status=P.FAILED)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(PAYMENT_LIST), {"status": "pending"})

        self.assertEqual(ids(response), {str(pending.pk)})

    def test_filter_by_provider(self):
        stripe = create_payment(self.order, provider=Payment.Provider.STRIPE)
        create_payment(self.order, provider=Payment.Provider.MTN_MOMO)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(PAYMENT_LIST), {"provider": "stripe"})

        self.assertEqual(ids(response), {str(stripe.pk)})

    def test_filter_by_payment_method(self):
        card = create_payment(self.order, method=Payment.PaymentMethod.CARD)
        create_payment(self.order, method=Payment.PaymentMethod.CASH)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(PAYMENT_LIST), {"payment_method": "card"})

        self.assertEqual(ids(response), {str(card.pk)})

    def test_filter_by_order(self):
        second_order = create_order(self.user)
        create_payment(self.order)
        target = create_payment(second_order)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(PAYMENT_LIST), {"order": str(second_order.pk)})

        self.assertEqual(ids(response), {str(target.pk)})

    def test_retrieve_hides_raw_gateway_payloads(self):
        payment = create_payment(self.order)
        PaymentTransaction.objects.create(
            payment=payment,
            provider_transaction_id="PROV-1",
            request_payload={"secret": "request"},
            response_payload={"secret": "response"},
            status=T.PENDING,
        )
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(PAYMENT_DETAIL, args=[payment.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["transactions"]), 1)
        summary = response.data["transactions"][0]
        self.assertEqual(summary["provider_transaction_id"], "PROV-1")
        self.assertNotIn("request_payload", summary)
        self.assertNotIn("response_payload", summary)

    def test_cannot_retrieve_other_customers_payment(self):
        payment = create_payment(self.other_order)
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse(PAYMENT_DETAIL, args=[payment.pk]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_can_retrieve_any_payment(self):
        payment = create_payment(self.order)
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse(PAYMENT_DETAIL, args=[payment.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)


# =====================================================
# PAYMENT UPDATE / DELETE RESTRICTIONS
# =====================================================

class PaymentMethodRestrictionTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.admin = create_user("admin", is_staff=True)
        self.payment = create_payment(create_order(self.user))
        self.url = reverse(PAYMENT_DETAIL, args=[self.payment.pk])

    def test_put_patch_delete_not_allowed(self):
        for user in (self.user, self.admin):
            self.client.force_authenticate(user)

            self.assertEqual(
                self.client.put(self.url, {}, format="json").status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
            )
            self.assertEqual(
                self.client.patch(self.url, {"amount": "1.00"}, format="json").status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
            )
            self.assertEqual(
                self.client.delete(self.url).status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
            )

        self.assertTrue(Payment.objects.filter(pk=self.payment.pk).exists())
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, Decimal("10000.00"))


# =====================================================
# PAYMENT CANCEL ACTION TESTS
# =====================================================

class PaymentCancelTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.other = create_user("bob")
        self.admin = create_user("admin", is_staff=True)
        self.order = create_order(self.user)

    def _cancel(self, payment):
        return self.client.post(reverse(PAYMENT_CANCEL, args=[payment.pk]), {}, format="json")

    def test_unauthenticated_denied(self):
        payment = create_payment(self.order)
        self.assertIn(self._cancel(payment).status_code, UNAUTHORIZED)

    def test_owner_can_cancel_pending_and_processing(self):
        self.client.force_authenticate(self.user)
        for current in [P.PENDING, P.PROCESSING]:
            payment = create_payment(self.order, payment_status=current)

            response = self._cancel(payment)

            self.assertEqual(response.status_code, status.HTTP_200_OK, current)
            payment.refresh_from_db()
            self.assertEqual(payment.status, P.CANCELLED)

    def test_cancel_response_body(self):
        payment = create_payment(self.order)
        self.client.force_authenticate(self.user)

        response = self._cancel(payment)

        self.assertTrue(response.data["message"])
        self.assertEqual(response.data["payment"]["status"], "cancelled")
        self.assertEqual(str(response.data["payment"]["id"]), str(payment.pk))

    def test_staff_can_cancel_any_payment(self):
        payment = create_payment(self.order)
        self.client.force_authenticate(self.admin)

        response = self._cancel(payment)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_other_customer_cannot_cancel(self):
        payment = create_payment(self.order)
        self.client.force_authenticate(self.other)

        response = self._cancel(payment)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        payment.refresh_from_db()
        self.assertEqual(payment.status, P.PENDING)

    def test_finished_payments_cannot_be_cancelled(self):
        self.client.force_authenticate(self.user)
        for current in [P.SUCCESSFUL, P.FAILED, P.CANCELLED, P.REFUNDED]:
            payment = create_payment(self.order, payment_status=current)

            response = self._cancel(payment)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, current)
            payment.refresh_from_db()
            self.assertEqual(payment.status, current)

    def test_cancelling_twice_is_rejected(self):
        payment = create_payment(self.order)
        self.client.force_authenticate(self.user)

        self.assertEqual(self._cancel(payment).status_code, status.HTTP_200_OK)
        self.assertEqual(self._cancel(payment).status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancelled_payment_does_not_block_a_new_one(self):
        payment = create_payment(self.order)
        self.client.force_authenticate(self.user)
        self._cancel(payment)

        response = self.client.post(
            reverse(PAYMENT_LIST),
            {
                "order": str(self.order.pk),
                "provider": "mtn_momo",
                "payment_method": "mobile_money",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(dec(response.data["amount"]), Decimal("10000.00"))

    def test_unknown_payment_returns_404(self):
        # The action uses Payment.objects.get(pk=pk), so an unknown id
        # currently raises DoesNotExist (500). Use get_object_or_404 to fix.
        self.client.raise_request_exception = False
        self.client.force_authenticate(self.user)

        response = self.client.post(
            reverse(PAYMENT_CANCEL, args=[MISSING_UUID]), {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# =====================================================
# PAYMENT UPDATE-STATUS ACTION TESTS
# =====================================================

class PaymentUpdateStatusTests(APITestCase):

    VALID = [
        (P.PENDING, P.PROCESSING),
        (P.PENDING, P.SUCCESSFUL),
        (P.PENDING, P.FAILED),
        (P.PENDING, P.CANCELLED),
        (P.PROCESSING, P.SUCCESSFUL),
        (P.PROCESSING, P.FAILED),
        (P.PROCESSING, P.CANCELLED),
        (P.SUCCESSFUL, P.REFUNDED),
    ]

    INVALID = [
        (P.PENDING, P.REFUNDED),
        (P.PENDING, P.PENDING),
        (P.PROCESSING, P.PENDING),
        (P.PROCESSING, P.REFUNDED),
        (P.SUCCESSFUL, P.FAILED),
        (P.SUCCESSFUL, P.CANCELLED),
        (P.SUCCESSFUL, P.PROCESSING),
        (P.FAILED, P.SUCCESSFUL),
        (P.CANCELLED, P.PENDING),
        (P.REFUNDED, P.SUCCESSFUL),
    ]

    EXPECTED_TX_STATUS = {
        P.PENDING: T.PENDING,
        P.PROCESSING: T.PENDING,
        P.SUCCESSFUL: T.SUCCESSFUL,
        P.FAILED: T.FAILED,
        P.CANCELLED: T.FAILED,
        P.REFUNDED: T.REVERSED,
    }

    def setUp(self):
        self.user = create_user("alice")
        self.admin = create_user("admin", is_staff=True)

    def _fresh_payment(self, current):
        order = create_order(self.user, total="10000.00")
        return create_payment(order, amount="10000.00", payment_status=current)

    def _post(self, payment, new_status, **extra):
        payload = {"status": new_status}
        payload.update(extra)
        return self.client.post(
            reverse(PAYMENT_UPDATE_STATUS, args=[payment.pk]), payload, format="json"
        )

    def test_unauthenticated_denied(self):
        payment = self._fresh_payment(P.PENDING)
        self.assertIn(self._post(payment, "processing").status_code, UNAUTHORIZED)

    def test_customer_cannot_update_status(self):
        payment = self._fresh_payment(P.PENDING)
        self.client.force_authenticate(self.user)

        response = self._post(payment, "successful", transaction_id="TX-1")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        payment.refresh_from_db()
        self.assertEqual(payment.status, P.PENDING)
        self.assertIsNone(payment.paid_at)

    def test_all_valid_transitions(self):
        self.client.force_authenticate(self.admin)

        for start, target in self.VALID:
            payment = self._fresh_payment(start)
            extra = {"note": f"{start}->{target}"}
            if target == P.SUCCESSFUL:
                extra["transaction_id"] = "TX-OK"

            response = self._post(payment, target, **extra)

            self.assertEqual(response.status_code, status.HTTP_200_OK, f"{start}->{target}")
            self.assertEqual(response.data["payment"]["status"], target)
            payment.refresh_from_db()
            self.assertEqual(payment.status, target)

            tx = payment.transactions.get()
            self.assertEqual(tx.status, self.EXPECTED_TX_STATUS[target], f"{start}->{target}")

    def test_all_invalid_transitions_rejected(self):
        self.client.force_authenticate(self.admin)

        for start, target in self.INVALID:
            payment = self._fresh_payment(start)

            response = self._post(payment, target, transaction_id="TX-X")

            self.assertEqual(
                response.status_code, status.HTTP_400_BAD_REQUEST, f"{start}->{target}"
            )
            payment.refresh_from_db()
            self.assertEqual(payment.status, start)
            self.assertEqual(payment.transactions.count(), 0)

    def test_successful_sets_paid_at_and_transaction_id(self):
        payment = self._fresh_payment(P.PROCESSING)
        self.client.force_authenticate(self.admin)

        response = self._post(payment, "successful", transaction_id="TX-123")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.transaction_id, "TX-123")
        self.assertIsNotNone(payment.paid_at)
        self.assertEqual(response.data["payment"]["transaction_id"], "TX-123")
        self.assertEqual(payment.transactions.get().provider_transaction_id, "TX-123")

    def test_successful_requires_transaction_id(self):
        payment = self._fresh_payment(P.PENDING)
        self.client.force_authenticate(self.admin)

        for extra in [{}, {"transaction_id": ""}]:
            response = self._post(payment, "successful", **extra)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("transaction_id", response.data)

        payment.refresh_from_db()
        self.assertEqual(payment.status, P.PENDING)
        self.assertIsNone(payment.paid_at)

    def test_non_successful_transitions_do_not_set_paid_at(self):
        payment = self._fresh_payment(P.PENDING)
        self.client.force_authenticate(self.admin)

        self._post(payment, "processing")

        payment.refresh_from_db()
        self.assertIsNone(payment.paid_at)

    def test_audit_transaction_records_who_and_why(self):
        payment = self._fresh_payment(P.PENDING)
        self.client.force_authenticate(self.admin)

        self._post(payment, "failed", note="Insufficient funds")

        tx = payment.transactions.get()
        self.assertEqual(tx.response_payload["updated_by"], self.admin.get_username())
        self.assertEqual(tx.response_payload["payment_status"], "failed")
        self.assertEqual(tx.response_payload["note"], "Insufficient funds")

    def test_refund_keeps_original_transaction_id(self):
        order = create_order(self.user)
        payment = create_payment(
            order, payment_status=P.SUCCESSFUL, transaction_id="TX-OLD"
        )
        self.client.force_authenticate(self.admin)

        response = self._post(payment, "refunded")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, P.REFUNDED)
        self.assertEqual(payment.transaction_id, "TX-OLD")
        self.assertEqual(payment.transactions.get().status, T.REVERSED)

    def test_overpayment_rejected(self):
        order = create_order(self.user, total="10000.00")
        create_payment(order, amount="8000.00", payment_status=P.SUCCESSFUL)
        payment = create_payment(order, amount="5000.00", payment_status=P.PENDING)
        self.client.force_authenticate(self.admin)

        response = self._post(payment, "successful", transaction_id="TX-OVER")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        payment.refresh_from_db()
        self.assertEqual(payment.status, P.PENDING)
        self.assertIsNone(payment.paid_at)

    def test_exact_payoff_allowed(self):
        order = create_order(self.user, total="10000.00")
        create_payment(order, amount="5000.00", payment_status=P.SUCCESSFUL)
        payment = create_payment(order, amount="5000.00", payment_status=P.PENDING)
        self.client.force_authenticate(self.admin)

        response = self._post(payment, "successful", transaction_id="TX-FINAL")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_two_pending_payments_cannot_both_succeed(self):
        order = create_order(self.user, total="10000.00")
        first = create_payment(order, amount="10000.00", payment_status=P.PENDING)
        second = create_payment(order, amount="10000.00", payment_status=P.PENDING)
        self.client.force_authenticate(self.admin)

        ok = self._post(first, "successful", transaction_id="TX-A")
        blocked = self._post(second, "successful", transaction_id="TX-B")

        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_status_rejected(self):
        payment = self._fresh_payment(P.PENDING)
        self.client.force_authenticate(self.admin)

        response = self._post(payment, "teleported")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_missing_status_rejected(self):
        payment = self._fresh_payment(P.PENDING)
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(PAYMENT_UPDATE_STATUS, args=[payment.pk]), {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_payment_returns_404(self):
        # Same Payment.objects.get(pk=pk) pattern: currently a 500.
        self.client.raise_request_exception = False
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse(PAYMENT_UPDATE_STATUS, args=[MISSING_UUID]),
            {"status": "processing"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# =====================================================
# PAYMENT TRANSACTION VIEWSET TESTS
# =====================================================

class PaymentTransactionViewSetTests(APITestCase):

    def setUp(self):
        self.user = create_user("alice")
        self.admin = create_user("admin", is_staff=True)
        self.payment_1 = create_payment(create_order(self.user))
        self.payment_2 = create_payment(create_order(self.user))
        self.tx_1 = PaymentTransaction.objects.create(
            payment=self.payment_1,
            provider_transaction_id="PROV-1",
            request_payload={"amount": "10000.00"},
            response_payload={"gateway": "ok"},
            status=T.SUCCESSFUL,
        )
        self.tx_2 = PaymentTransaction.objects.create(
            payment=self.payment_2, status=T.FAILED
        )

    def test_unauthenticated_denied(self):
        self.assertIn(self.client.get(reverse(TX_LIST)).status_code, UNAUTHORIZED)

    def test_customer_cannot_list_or_retrieve(self):
        self.client.force_authenticate(self.user)

        listing = self.client.get(reverse(TX_LIST))
        detail = self.client.get(reverse(TX_DETAIL, args=[self.tx_1.pk]))

        self.assertEqual(listing.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(detail.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_sees_all_transactions(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse(TX_LIST))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ids(response), {str(self.tx_1.pk), str(self.tx_2.pk)})

    def test_staff_sees_raw_payloads(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse(TX_DETAIL, args=[self.tx_1.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["request_payload"], {"amount": "10000.00"})
        self.assertEqual(response.data["response_payload"], {"gateway": "ok"})
        self.assertEqual(str(response.data["payment"]), str(self.payment_1.pk))

    def test_filter_by_payment(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(TX_LIST), {"payment": str(self.payment_2.pk)})
        self.assertEqual(ids(response), {str(self.tx_2.pk)})

    def test_filter_by_status(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse(TX_LIST), {"status": "successful"})
        self.assertEqual(ids(response), {str(self.tx_1.pk)})

    def test_read_only(self):
        self.client.force_authenticate(self.admin)
        url = reverse(TX_DETAIL, args=[self.tx_1.pk])

        self.assertEqual(
            self.client.post(reverse(TX_LIST), {}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.patch(url, {"status": "failed"}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def test_transactions_created_by_the_api_are_visible_to_staff(self):
        self.client.force_authenticate(self.user)
        order = create_order(self.user)
        created = self.client.post(
            reverse(PAYMENT_LIST),
            {
                "order": str(order.pk),
                "provider": "stripe",
                "payment_method": "card",
            },
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.admin)
        response = self.client.get(
            reverse(TX_LIST), {"payment": str(created.data["id"])}
        )

        data = results(response)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["status"], "initiated")