"""Read-only querysets for the notifications domain."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import QuerySet

from .models import Notification


def get_notifications_for_user(user: User, unread_only: bool = False) -> QuerySet:
    """Return notifications for a user, newest first. Optionally filter to unread only."""
    qs = Notification.objects.filter(recipient=user)
    if unread_only:
        qs = qs.filter(is_read=False)
    return qs


def get_notification_by_id(notification_id: int, user: User) -> Notification:
    """
    Return a single notification belonging to user.
    Raises Notification.DoesNotExist if not found or not owned by user.
    """
    return Notification.objects.get(pk=notification_id, recipient=user)
