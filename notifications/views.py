"""
Notification API views.

All endpoints are scoped to the authenticated user — a user can only
see and act on their own notifications.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin

from .models import Notification
from .selectors import get_notifications_for_user
from .serializers import NotificationSerializer
from .services import NotificationService


class NotificationViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """
    Notification inbox for the authenticated user.

    - list: returns all notifications (newest first), filterable by ?unread=true
    - retrieve: single notification detail
    - mark_read: POST /<id>/mark_read/ — mark one as read
    - mark_all_read: POST /mark_all_read/ — mark all as read
    - unread_count: GET /unread_count/ — badge count
    """

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        unread_only = self.request.query_params.get("unread", "").lower() == "true"
        return get_notifications_for_user(self.request.user, unread_only=unread_only)

    @extend_schema(
        summary="Mark a single notification as read",
        responses={200: NotificationSerializer},
    )
    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        try:
            notification = NotificationService.mark_read(notification, request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(NotificationSerializer(notification).data)

    @extend_schema(
        summary="Mark all notifications as read",
        responses={200: {"type": "object", "properties": {"marked_read": {"type": "integer"}}}},
    )
    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        count = NotificationService.mark_all_read(request.user)
        return Response({"marked_read": count})

    @extend_schema(
        summary="Unread notification count (for badge display)",
        responses={200: {"type": "object", "properties": {"unread_count": {"type": "integer"}}}},
        parameters=[
            OpenApiParameter(name="unread", description="Filter unread only", required=False, type=str),
        ],
    )
    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        count = NotificationService.unread_count(request.user)
        return Response({"unread_count": count})
