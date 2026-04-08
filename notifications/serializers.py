"""Serializers for the notifications app."""

from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    notification_type_display = serializers.CharField(
        source="get_notification_type_display", read_only=True
    )

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "notification_type_display",
            "title",
            "body",
            "is_read",
            "read_at",
            "extra_data",
            "created_at",
        ]
        read_only_fields = fields
