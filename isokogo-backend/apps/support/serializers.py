
from rest_framework import serializers

from .models import SupportTicket


class SupportTicketSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    customer_email = serializers.EmailField(
        source="customer.email",
        read_only=True
    )
    assigned_to_name = serializers.SerializerMethodField()
    order_number = serializers.CharField(
        source="order.order_number",
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "ticket_number",
            "customer",
            "customer_name",
            "customer_email",
            "order",
            "order_number",
            "subject",
            "description",
            "category",
            "priority",
            "status",
            "assigned_to",
            "assigned_to_name",
            "resolution_notes",
            "created_at",
            "updated_at",
            "resolved_at",
            "closed_at",
        ]

        read_only_fields = [
            "id",
            "ticket_number",
            "customer",
            "customer_name",
            "customer_email",
            "order_number",
            "status",
            "assigned_to",
            "assigned_to_name",
            "resolution_notes",
            "created_at",
            "updated_at",
            "resolved_at",
            "closed_at",
        ]

    def get_customer_name(self, obj):
        return (
            obj.customer.get_full_name()
            or obj.customer.get_username()
        )

    def get_assigned_to_name(self, obj):
        if not obj.assigned_to:
            return None

        return (
            obj.assigned_to.get_full_name()
            or obj.assigned_to.get_username()
        )

    def validate_order(self, order):
        request = self.context.get("request")

        if (
            request
            and request.user.is_authenticated
            and not request.user.is_staff
            and order.customer_id != request.user.id
        ):
            raise serializers.ValidationError(
                "You can only create support tickets for your own orders."
            )

        return order

    def validate(self, attrs):
        request = self.context.get("request")

        if self.instance and request and not request.user.is_staff:
            allowed_statuses = [
                SupportTicket.Status.OPEN,
                SupportTicket.Status.WAITING_CUSTOMER,
            ]

            if self.instance.status not in allowed_statuses:
                raise serializers.ValidationError(
                    "You cannot edit a ticket that is already being processed or closed."
                )

            allowed_fields = {"description"}

            submitted_fields = set(self.initial_data.keys())

            forbidden_fields = submitted_fields - allowed_fields

            if forbidden_fields:
                raise serializers.ValidationError(
                    "Customers can only update the ticket description."
                )

        return attrs


class SupportTicketStaffSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    order_number = serializers.CharField(
        source="order.order_number",
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "ticket_number",
            "customer",
            "customer_name",
            "order",
            "order_number",
            "subject",
            "description",
            "category",
            "priority",
            "status",
            "assigned_to",
            "assigned_to_name",
            "resolution_notes",
            "created_at",
            "updated_at",
            "resolved_at",
            "closed_at",
        ]

        read_only_fields = [
            "id",
            "ticket_number",
            "customer",
            "customer_name",
            "order_number",
            "subject",
            "description",
            "category",
            "created_at",
            "updated_at",
            "resolved_at",
            "closed_at",
        ]

    def get_customer_name(self, obj):
        return (
            obj.customer.get_full_name()
            or obj.customer.get_username()
        )

    def get_assigned_to_name(self, obj):
        if not obj.assigned_to:
            return None

        return (
            obj.assigned_to.get_full_name()
            or obj.assigned_to.get_username()
        )

    def validate_assigned_to(self, user):
        if user and not user.is_staff:
            raise serializers.ValidationError(
                "Only staff members can be assigned support tickets."
            )

        return user
