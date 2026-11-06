
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import (
    NotificationSerializer,
    CreateNotificationSerializer,
)


class NotificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    queryset = Notification.objects.select_related(
        "recipient",
        "related_order",
    ).all()

    def get_queryset(self):
        queryset = super().get_queryset()

        # Users can only access their own notifications.
        if not self.request.user.is_staff:
            queryset = queryset.filter(
                recipient=self.request.user
            )

        notification_type = self.request.query_params.get(
            "notification_type"
        )
        is_read = self.request.query_params.get("is_read")

        if notification_type:
            queryset = queryset.filter(
                notification_type=notification_type
            )

        if is_read is not None:
            queryset = queryset.filter(
                is_read=is_read.lower() == "true"
            )

        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return CreateNotificationSerializer

        return NotificationSerializer

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied(
                "Only staff members can create notifications."
            )

        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save()

    def update(self, request, *args, **kwargs):
        raise PermissionDenied(
            "Use the notification actions to update notification status."
        )

    def partial_update(self, request, *args, **kwargs):
        raise PermissionDenied(
            "Use the notification actions to update notification status."
        )

    @action(detail=True, methods=["post"])
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()

        notification.is_read = True
        notification.save(update_fields=["is_read"])

        return Response({
            "message": "Notification marked as read.",
            "notification": NotificationSerializer(notification).data,
        })

    @action(detail=True, methods=["post"])
    def mark_as_unread(self, request, pk=None):
        notification = self.get_object()

        notification.is_read = False
        notification.save(update_fields=["is_read"])

        return Response({
            "message": "Notification marked as unread.",
            "notification": NotificationSerializer(notification).data,
        })

    @action(detail=False, methods=["post"])
    def mark_all_as_read(self, request):
        updated_count = self.get_queryset().filter(
            is_read=False
        ).update(is_read=True)

        return Response({
            "message": "Notifications marked as read.",
            "updated_count": updated_count,
        })

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        count = self.get_queryset().filter(
            is_read=False
        ).count()

        return Response({
            "unread_count": count,
        })

    @action(detail=False, methods=["delete"])
    def clear_read(self, request):
        deleted_count, _ = self.get_queryset().filter(
            is_read=True
        ).delete()

        return Response({
            "message": "Read notifications cleared.",
            "deleted_count": deleted_count,
        })
