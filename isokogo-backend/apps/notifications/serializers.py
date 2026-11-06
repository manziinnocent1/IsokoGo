
from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    recipient_name = serializers.SerializerMethodField()
    order_number = serializers.CharField(
        source="related_order.order_number",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Notification
        fields = [
            "id",
            "recipient",
            "recipient_name",
            "title",
            "message",
            "notification_type",
            "is_read",
            "related_order",
            "order_number",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "recipient",
            "recipient_name",
            "created_at",
        ]

    def get_recipient_name(self, obj):
        return (
            obj.recipient.get_full_name()
            or obj.recipient.get_username()
        )

    def validate(self, attrs):
        notification_type = attrs.get(
            "notification_type",
            getattr(
                self.instance,
                "notification_type",
                Notification.NotificationType.SYSTEM,
            ),
        )

        if notification_type not in Notification.NotificationType.values:
            raise serializers.ValidationError({
                "notification_type": "Invalid notification type."
            })

        return attrs


class CreateNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "recipient",
            "title",
            "message",
            "notification_type",
            "related_order",
        ]

    def validate(self, attrs):
        related_order = attrs.get("related_order")
        recipient = attrs.get("recipient")

        if related_order and recipient:
            if related_order.customer_id != recipient.id:
                raise serializers.ValidationError({
                    "related_order": (
                        "The selected order does not belong to this recipient."
                    )
                })

        return attrs
