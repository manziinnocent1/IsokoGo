
import pytest

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from .models import SupportTicket
from .serializers import (
    SupportTicketSerializer,
    SupportTicketStaffSerializer,
)


User = get_user_model()


# ============================================================
# FIXTURES
# ============================================================

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
def another_staff_user(db):
    return User.objects.create_user(
        email="staff2@example.com",
        password="StaffPassword123!",
        is_staff=True,
    )


@pytest.fixture
def customer_request(customer):
    factory = APIRequestFactory()
    request = factory.post("/api/support/tickets/")
    request.user = customer
    return request


@pytest.fixture
def staff_request(staff_user):
    factory = APIRequestFactory()
    request = factory.patch("/api/support/tickets/")
    request.user = staff_user
    return request


@pytest.fixture
def support_ticket(db, customer):
    return SupportTicket.objects.create(
        customer=customer,
        subject="Payment problem",
        description=(
            "I made a payment but my order "
            "has not been confirmed."
        ),
        category=SupportTicket.Category.PAYMENT,
        priority=SupportTicket.Priority.HIGH,
    )


@pytest.fixture
def another_support_ticket(db, another_customer):
    return SupportTicket.objects.create(
        customer=another_customer,
        subject="Delivery problem",
        description=(
            "My delivery has not arrived "
            "at the expected time."
        ),
        category=SupportTicket.Category.DELIVERY,
    )


# ============================================================
# SUPPORT TICKET MODEL TESTS
# ============================================================

@pytest.mark.django_db
class TestSupportTicketModel:

    def test_create_support_ticket(self, support_ticket):
        assert support_ticket.subject == "Payment problem"
        assert support_ticket.category == SupportTicket.Category.PAYMENT

    def test_ticket_has_uuid(self, support_ticket):
        assert support_ticket.id is not None

    def test_ticket_number_is_generated_automatically(
        self,
        support_ticket,
    ):
        assert support_ticket.ticket_number.startswith("ISO-")
        assert len(support_ticket.ticket_number) == 14

    def test_ticket_number_is_unique(
        self,
        support_ticket,
        another_customer,
    ):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SupportTicket.objects.create(
                    ticket_number=support_ticket.ticket_number,
                    customer=another_customer,
                    subject="Another issue",
                    description="Another support ticket description.",
                )

    def test_default_category(self, db, customer):
        ticket = SupportTicket.objects.create(
            customer=customer,
            subject="General inquiry",
            description="I need help with my account.",
        )

        assert ticket.category == SupportTicket.Category.GENERAL

    def test_default_priority(self, db, customer):
        ticket = SupportTicket.objects.create(
            customer=customer,
            subject="General inquiry",
            description="I need help with my account.",
        )

        assert ticket.priority == SupportTicket.Priority.MEDIUM

    def test_default_status(self, db, customer):
        ticket = SupportTicket.objects.create(
            customer=customer,
            subject="General inquiry",
            description="I need help with my account.",
        )

        assert ticket.status == SupportTicket.Status.OPEN

    def test_order_is_optional(self, support_ticket):
        assert support_ticket.order is None

    def test_assigned_to_is_optional(self, support_ticket):
        assert support_ticket.assigned_to is None

    def test_resolution_notes_default_to_none(self, support_ticket):
        assert support_ticket.resolution_notes is None

    def test_resolved_at_default_to_none(self, support_ticket):
        assert support_ticket.resolved_at is None

    def test_closed_at_default_to_none(self, support_ticket):
        assert support_ticket.closed_at is None

    def test_ticket_string_representation(self, support_ticket):
        expected = (
            f"{support_ticket.ticket_number} - "
            f"{support_ticket.subject}"
        )

        assert str(support_ticket) == expected

    def test_ticket_customer_relationship(self, support_ticket, customer):
        assert support_ticket.customer == customer
        assert support_ticket in customer.support_tickets.all()

    def test_ticket_ordering(self, support_ticket):
        tickets = SupportTicket.objects.all()

        assert tickets.first() == support_ticket

    def test_all_priority_choices(self):
        expected = [
            "low",
            "medium",
            "high",
            "urgent",
        ]

        actual = [
            choice[0]
            for choice in SupportTicket.Priority.choices
        ]

        assert actual == expected

    def test_all_status_choices(self):
        expected = [
            "open",
            "in_progress",
            "waiting_customer",
            "resolved",
            "closed",
        ]

        actual = [
            choice[0]
            for choice in SupportTicket.Status.choices
        ]

        assert actual == expected

    def test_all_category_choices(self):
        expected = [
            "general",
            "order",
            "payment",
            "delivery",
            "refund",
            "product",
            "account",
            "other",
        ]

        actual = [
            choice[0]
            for choice in SupportTicket.Category.choices
        ]

        assert actual == expected

    def test_ticket_number_does_not_change_on_update(
        self,
        support_ticket,
    ):
        original_number = support_ticket.ticket_number

        support_ticket.subject = "Updated payment problem"
        support_ticket.save()

        support_ticket.refresh_from_db()

        assert support_ticket.ticket_number == original_number


# ============================================================
# CUSTOMER SUPPORT TICKET SERIALIZER TESTS
# ============================================================

@pytest.mark.django_db
class TestSupportTicketSerializer:

    def test_valid_ticket_serializer(self, customer_request):
        serializer = SupportTicketSerializer(
            data={
                "subject": "Payment problem",
                "description": (
                    "I made a payment but my order "
                    "has not been confirmed."
                ),
                "category": SupportTicket.Category.PAYMENT,
                "priority": SupportTicket.Priority.HIGH,
            },
            context={"request": customer_request},
        )

        assert serializer.is_valid(), serializer.errors

    def test_ticket_subject_is_required(self, customer_request):
        serializer = SupportTicketSerializer(
            data={
                "description": "I need help with my order.",
            },
            context={"request": customer_request},
        )

        assert not serializer.is_valid()
        assert "subject" in serializer.errors

    def test_ticket_description_is_required(self, customer_request):
        serializer = SupportTicketSerializer(
            data={
                "subject": "Payment problem",
            },
            context={"request": customer_request},
        )

        assert not serializer.is_valid()
        assert "description" in serializer.errors

    def test_description_must_have_at_least_ten_characters(
        self,
        customer_request,
    ):
        serializer = SupportTicketSerializer(
            data={
                "subject": "Payment problem",
                "description": "Help",
            },
            context={"request": customer_request},
        )

        assert not serializer.is_valid()
        assert "description" in serializer.errors

    def test_description_with_ten_characters_is_valid(
        self,
        customer_request,
    ):
        serializer = SupportTicketSerializer(
            data={
                "subject": "Payment problem",
                "description": "Need help!!",
            },
            context={"request": customer_request},
        )

        assert serializer.is_valid(), serializer.errors

    def test_invalid_category_is_rejected(self, customer_request):
        serializer = SupportTicketSerializer(
            data={
                "subject": "Payment problem",
                "description": "I need help with my payment.",
                "category": "invalid_category",
            },
            context={"request": customer_request},
        )

        assert not serializer.is_valid()
        assert "category" in serializer.errors

    def test_invalid_priority_is_rejected(self, customer_request):
        serializer = SupportTicketSerializer(
            data={
                "subject": "Payment problem",
                "description": "I need help with my payment.",
                "priority": "critical",
            },
            context={"request": customer_request},
        )

        assert not serializer.is_valid()
        assert "priority" in serializer.errors

    def test_customer_cannot_set_ticket_status(
        self,
        customer_request,
    ):
        serializer = SupportTicketSerializer(
            data={
                "subject": "Payment problem",
                "description": "I need help with my payment.",
                "status": SupportTicket.Status.RESOLVED,
            },
            context={"request": customer_request},
        )

        assert serializer.is_valid(), serializer.errors

        assert (
            "status"
            not in serializer.validated_data
        )

    def test_customer_cannot_assign_ticket(
        self,
        customer_request,
        staff_user,
    ):
        serializer = SupportTicketSerializer(
            data={
                "subject": "Payment problem",
                "description": "I need help with my payment.",
                "assigned_to": str(staff_user.id),
            },
            context={"request": customer_request},
        )

        assert serializer.is_valid(), serializer.errors

        assert "assigned_to" not in serializer.validated_data

    def test_customer_cannot_set_resolution_notes(
        self,
        customer_request,
    ):
        serializer = SupportTicketSerializer(
            data={
                "subject": "Payment problem",
                "description": "I need help with my payment.",
                "resolution_notes": "Issue resolved.",
            },
            context={"request": customer_request},
        )

        assert serializer.is_valid(), serializer.errors

        assert "resolution_notes" not in serializer.validated_data

    def test_customer_name_is_returned(
        self,
        support_ticket,
    ):
        serializer = SupportTicketSerializer(support_ticket)

        assert "customer_name" in serializer.data

    def test_customer_email_is_returned(
        self,
        support_ticket,
    ):
        serializer = SupportTicketSerializer(support_ticket)

        assert (
            serializer.data["customer_email"]
            == "customer@example.com"
        )

    def test_ticket_number_is_returned(
        self,
        support_ticket,
    ):
        serializer = SupportTicketSerializer(support_ticket)

        assert (
            serializer.data["ticket_number"]
            == support_ticket.ticket_number
        )

    def test_assigned_to_name_is_none_when_unassigned(
        self,
        support_ticket,
    ):
        serializer = SupportTicketSerializer(support_ticket)

        assert serializer.data["assigned_to_name"] is None

    def test_customer_cannot_edit_processed_ticket(
        self,
        support_ticket,
        customer_request,
    ):
        support_ticket.status = SupportTicket.Status.IN_PROGRESS
        support_ticket.save()

        serializer = SupportTicketSerializer(
            support_ticket,
            data={
                "description": "I need to update this ticket.",
            },
            partial=True,
            context={"request": customer_request},
        )

        assert not serializer.is_valid()
        assert "non_field_errors" in serializer.errors

    def test_customer_can_edit_open_ticket_description(
        self,
        support_ticket,
        customer_request,
    ):
        serializer = SupportTicketSerializer(
            support_ticket,
            data={
                "description": "I have additional information.",
            },
            partial=True,
            context={"request": customer_request},
        )

        assert serializer.is_valid(), serializer.errors

    def test_customer_can_edit_waiting_ticket_description(
        self,
        support_ticket,
        customer_request,
    ):
        support_ticket.status = SupportTicket.Status.WAITING_CUSTOMER
        support_ticket.save()

        serializer = SupportTicketSerializer(
            support_ticket,
            data={
                "description": "Here is the requested information.",
            },
            partial=True,
            context={"request": customer_request},
        )

        assert serializer.is_valid(), serializer.errors

    def test_customer_cannot_update_ticket_subject(
        self,
        support_ticket,
        customer_request,
    ):
        serializer = SupportTicketSerializer(
            support_ticket,
            data={
                "subject": "New subject",
            },
            partial=True,
            context={"request": customer_request},
        )

        assert not serializer.is_valid()

    def test_customer_cannot_update_ticket_category(
        self,
        support_ticket,
        customer_request,
    ):
        serializer = SupportTicketSerializer(
            support_ticket,
            data={
                "category": SupportTicket.Category.REFUND,
            },
            partial=True,
            context={"request": customer_request},
        )

        assert not serializer.is_valid()

    def test_customer_cannot_update_ticket_priority(
        self,
        support_ticket,
        customer_request,
    ):
        serializer = SupportTicketSerializer(
            support_ticket,
            data={
                "priority": SupportTicket.Priority.URGENT,
            },
            partial=True,
            context={"request": customer_request},
        )

        assert not serializer.is_valid()


# ============================================================
# STAFF SUPPORT TICKET SERIALIZER TESTS
# ============================================================

@pytest.mark.django_db
class TestSupportTicketStaffSerializer:

    def test_staff_serializer_returns_ticket(
        self,
        support_ticket,
    ):
        serializer = SupportTicketStaffSerializer(support_ticket)

        assert serializer.data["subject"] == "Payment problem"

    def test_staff_can_update_ticket_status(
        self,
        support_ticket,
    ):
        serializer = SupportTicketStaffSerializer(
            support_ticket,
            data={
                "status": SupportTicket.Status.IN_PROGRESS,
            },
            partial=True,
        )

        assert serializer.is_valid(), serializer.errors

    def test_staff_can_update_ticket_priority(
        self,
        support_ticket,
    ):
        serializer = SupportTicketStaffSerializer(
            support_ticket,
            data={
                "priority": SupportTicket.Priority.URGENT,
            },
            partial=True,
        )

        assert serializer.is_valid(), serializer.errors

    def test_staff_can_update_resolution_notes(
        self,
        support_ticket,
    ):
        serializer = SupportTicketStaffSerializer(
            support_ticket,
            data={
                "resolution_notes": "Payment issue resolved.",
            },
            partial=True,
        )

        assert serializer.is_valid(), serializer.errors

    def test_staff_can_assign_ticket_to_staff(
        self,
        support_ticket,
        another_staff_user,
    ):
        serializer = SupportTicketStaffSerializer(
            support_ticket,
            data={
                "assigned_to": str(another_staff_user.id),
            },
            partial=True,
        )

        assert serializer.is_valid(), serializer.errors

    def test_staff_cannot_assign_ticket_to_customer(
        self,
        support_ticket,
        customer,
    ):
        serializer = SupportTicketStaffSerializer(
            support_ticket,
            data={
                "assigned_to": str(customer.id),
            },
            partial=True,
        )

        assert not serializer.is_valid()
        assert "assigned_to" in serializer.errors

    def test_staff_can_leave_ticket_unassigned(
        self,
        support_ticket,
    ):
        serializer = SupportTicketStaffSerializer(
            support_ticket,
            data={
                "assigned_to": None,
            },
            partial=True,
        )

        assert serializer.is_valid(), serializer.errors

    def test_staff_cannot_change_customer(
        self,
        support_ticket,
        another_customer,
    ):
        serializer = SupportTicketStaffSerializer(
            support_ticket,
            data={
                "customer": str(another_customer.id),
            },
            partial=True,
        )

        assert serializer.is_valid(), serializer.errors

        assert "customer" not in serializer.validated_data

    def test_staff_cannot_change_subject(
        self,
        support_ticket,
    ):
        serializer = SupportTicketStaffSerializer(
            support_ticket,
            data={
                "subject": "Changed subject",
            },
            partial=True,
        )

        assert serializer.is_valid(), serializer.errors

        assert "subject" not in serializer.validated_data

    def test_staff_cannot_change_description(
        self,
        support_ticket,
    ):
        serializer = SupportTicketStaffSerializer(
            support_ticket,
            data={
                "description": "Changed description.",
            },
            partial=True,
        )

        assert serializer.is_valid(), serializer.errors

        assert "description" not in serializer.validated_data

    def test_staff_can_return_assigned_to_name(
        self,
        support_ticket,
        staff_user,
    ):
        support_ticket.assigned_to = staff_user
        support_ticket.save()

        serializer = SupportTicketStaffSerializer(support_ticket)

        assert serializer.data["assigned_to_name"] is not None
