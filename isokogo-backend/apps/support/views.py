
from django.db import transaction
from django.utils import timezone

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import SupportTicket
from .serializers import (
    SupportTicketSerializer,
    SupportTicketStaffSerializer,
)


class SupportTicketViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    http_method_names = [
        "get",
        "post",
        "patch",
        "head",
        "options",
    ]

    def get_queryset(self):
        queryset = SupportTicket.objects.select_related(
            "customer",
            "order",
            "assigned_to",
        )

        user = self.request.user

        # Staff members can see all support tickets.
        if user.is_staff:
            return queryset

        # Customers can only see their own tickets.
        return queryset.filter(customer=user)

    def get_serializer_class(self):
        if self.request.user.is_staff:
            return SupportTicketStaffSerializer

        return SupportTicketSerializer

    def perform_create(self, serializer):
        serializer.save(
            customer=self.request.user,
            status=SupportTicket.Status.OPEN,
            priority=SupportTicket.Priority.MEDIUM,
        )

    def update(self, request, *args, **kwargs):
        """
        Customers can only update their descriptions.
        Staff can update ticket management fields.
        """

        if not request.user.is_staff and not kwargs.get("partial", False):
            raise PermissionDenied(
                "Use PATCH to update your support ticket."
            )

        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        """
        Lock the ticket before changing its status to prevent
        conflicting status updates.
        """

        with transaction.atomic():
            ticket = SupportTicket.objects.select_for_update().get(
                pk=serializer.instance.pk
            )

            if not self.request.user.is_staff:
                if ticket.status not in [
                    SupportTicket.Status.OPEN,
                    SupportTicket.Status.WAITING_CUSTOMER,
                ]:
                    raise PermissionDenied(
                        "You cannot update a ticket in its current status."
                    )

                serializer.save()
                return

            old_status = ticket.status
            new_status = serializer.validated_data.get(
                "status",
                old_status,
            )

            allowed_transitions = {
                SupportTicket.Status.OPEN: [
                    SupportTicket.Status.IN_PROGRESS,
                    SupportTicket.Status.WAITING_CUSTOMER,
                    SupportTicket.Status.RESOLVED,
                ],
                SupportTicket.Status.IN_PROGRESS: [
                    SupportTicket.Status.WAITING_CUSTOMER,
                    SupportTicket.Status.RESOLVED,
                ],
                SupportTicket.Status.WAITING_CUSTOMER: [
                    SupportTicket.Status.IN_PROGRESS,
                    SupportTicket.Status.RESOLVED,
                ],
                SupportTicket.Status.RESOLVED: [
                    SupportTicket.Status.CLOSED,
                ],
                SupportTicket.Status.CLOSED: [],
            }

            if (
                new_status != old_status
                and new_status not in allowed_transitions.get(old_status, [])
            ):
                raise ValidationError({
                    "status": (
                        f"Cannot change ticket status from "
                        f"{old_status} to {new_status}."
                    )
                })

            extra_fields = {}

            if new_status == SupportTicket.Status.RESOLVED:
                if not ticket.resolved_at:
                    extra_fields["resolved_at"] = timezone.now()

            elif new_status == SupportTicket.Status.CLOSED:
                if not ticket.resolved_at:
                    extra_fields["resolved_at"] = timezone.now()

                if not ticket.closed_at:
                    extra_fields["closed_at"] = timezone.now()

            serializer.save(**extra_fields)

    def destroy(self, request, *args, **kwargs):
        raise PermissionDenied(
            "Support tickets cannot be deleted. "
            "Close the ticket instead."
        )

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.IsAdminUser],
        url_path="statistics",
    )
    def statistics(self, request):
        """
        Staff dashboard statistics.

        GET /api/support/tickets/statistics/
        """

        queryset = SupportTicket.objects.all()

        return Response({
            "total_tickets": queryset.count(),
            "open_tickets": queryset.filter(
                status=SupportTicket.Status.OPEN
            ).count(),
            "in_progress_tickets": queryset.filter(
                status=SupportTicket.Status.IN_PROGRESS
            ).count(),
            "waiting_customer_tickets": queryset.filter(
                status=SupportTicket.Status.WAITING_CUSTOMER
            ).count(),
            "resolved_tickets": queryset.filter(
                status=SupportTicket.Status.RESOLVED
            ).count(),
            "closed_tickets": queryset.filter(
                status=SupportTicket.Status.CLOSED
            ).count(),
            "urgent_tickets": queryset.filter(
                priority=SupportTicket.Priority.URGENT
            ).exclude(
                status__in=[
                    SupportTicket.Status.RESOLVED,
                    SupportTicket.Status.CLOSED,
                ]
            ).count(),
        })

    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[permissions.IsAdminUser],
        url_path="assign",
    )
    def assign(self, request, pk=None):
        """
        Assign a support ticket to a staff member.

        PATCH /api/support/tickets/{id}/assign/
        """

        ticket = self.get_object()

        assigned_to_id = request.data.get("assigned_to")

        if not assigned_to_id:
            raise ValidationError({
                "assigned_to": "A staff user ID is required."
            })

        from django.contrib.auth import get_user_model

        User = get_user_model()

        assigned_user = User.objects.filter(
            pk=assigned_to_id,
            is_staff=True,
            is_active=True,
        ).first()

        if not assigned_user:
            raise ValidationError({
                "assigned_to": "The selected staff member does not exist or is inactive."
            })

        ticket.assigned_to = assigned_user

        if ticket.status == SupportTicket.Status.OPEN:
            ticket.status = SupportTicket.Status.IN_PROGRESS

        ticket.save(
            update_fields=[
                "assigned_to",
                "status",
                "updated_at",
            ]
        )

        return Response({
            "message": "Support ticket assigned successfully.",
            "ticket": SupportTicketStaffSerializer(
                ticket,
                context={"request": request},
            ).data,
        })

    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[permissions.IsAdminUser],
        url_path="status",
    )
    def update_status(self, request, pk=None):
        """
        Update ticket status and optionally add resolution notes.

        PATCH /api/support/tickets/{id}/status/
        """

        ticket = self.get_object()

        new_status = request.data.get("status")

        if not new_status:
            raise ValidationError({
                "status": "Status is required."
            })

        if new_status not in SupportTicket.Status.values:
            raise ValidationError({
                "status": "Invalid support ticket status."
            })

        resolution_notes = request.data.get("resolution_notes")

        with transaction.atomic():
            ticket = SupportTicket.objects.select_for_update().get(
                pk=ticket.pk
            )

            allowed_transitions = {
                SupportTicket.Status.OPEN: [
                    SupportTicket.Status.IN_PROGRESS,
                    SupportTicket.Status.WAITING_CUSTOMER,
                    SupportTicket.Status.RESOLVED,
                ],
                SupportTicket.Status.IN_PROGRESS: [
                    SupportTicket.Status.WAITING_CUSTOMER,
                    SupportTicket.Status.RESOLVED,
                ],
                SupportTicket.Status.WAITING_CUSTOMER: [
                    SupportTicket.Status.IN_PROGRESS,
                    SupportTicket.Status.RESOLVED,
                ],
                SupportTicket.Status.RESOLVED: [
                    SupportTicket.Status.CLOSED,
                ],
                SupportTicket.Status.CLOSED: [],
            }

            if (
                new_status != ticket.status
                and new_status not in allowed_transitions[ticket.status]
            ):
                raise ValidationError({
                    "status": "This status transition is not allowed."
                })

            ticket.status = new_status

            if resolution_notes is not None:
                ticket.resolution_notes = resolution_notes

            if new_status == SupportTicket.Status.RESOLVED:
                if not ticket.resolved_at:
                    ticket.resolved_at = timezone.now()

            if new_status == SupportTicket.Status.CLOSED:
                if not ticket.resolved_at:
                    ticket.resolved_at = timezone.now()

                if not ticket.closed_at:
                    ticket.closed_at = timezone.now()

            ticket.save()

        return Response({
            "message": "Support ticket status updated successfully.",
            "ticket": SupportTicketStaffSerializer(
                ticket,
                context={"request": request},
            ).data,
        })

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.IsAdminUser],
        url_path="unassigned",
    )
    def unassigned(self, request):
        """
        Staff list of tickets that have not been assigned.

        GET /api/support/tickets/unassigned/
        """

        tickets = self.get_queryset().filter(
            assigned_to__isnull=True
        ).exclude(
            status__in=[
                SupportTicket.Status.RESOLVED,
                SupportTicket.Status.CLOSED,
            ]
        )

        page = self.paginate_queryset(tickets)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(tickets, many=True)

        return Response(serializer.data)
