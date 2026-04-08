"""
API tests for NotificationViewSet:
  - list (GET /api/v1/notifications/)
  - retrieve (GET /api/v1/notifications/<id>/)
  - mark_read (POST /api/v1/notifications/<id>/mark_read/)
  - mark_all_read (POST /api/v1/notifications/mark_all_read/)
  - unread_count (GET /api/v1/notifications/unread_count/)
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from factories import UserFactory
from notifications.models import Notification
from notifications.services import NotificationService

BASE_URL = "/api/v1/notifications/"


def detail_url(pk):
    return f"{BASE_URL}{pk}/"


def mark_read_url(pk):
    return f"{BASE_URL}{pk}/mark_read/"


MARK_ALL_URL = f"{BASE_URL}mark_all_read/"
UNREAD_COUNT_URL = f"{BASE_URL}unread_count/"


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def other_user(db):
    return UserFactory()


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture
def notification(user):
    return NotificationService.create(
        recipient=user,
        notification_type=Notification.NotificationType.BELT_PROMOTION,
        title="Blue Belt!",
        body="Congrats!",
    )


def _make_notifications(user, count, notification_type=None):
    ntype = notification_type or Notification.NotificationType.BELT_PROMOTION
    return [
        NotificationService.create(recipient=user, notification_type=ntype, title=f"Notif {i}")
        for i in range(count)
    ]


# ─── Auth guard ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAuthGuard:
    def test_unauthenticated_list_returns_401(self, anon_client):
        response = anon_client.get(BASE_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthenticated_mark_all_read_returns_401(self, anon_client):
        response = anon_client.post(MARK_ALL_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthenticated_unread_count_returns_401(self, anon_client):
        response = anon_client.get(UNREAD_COUNT_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── list ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestNotificationList:
    def test_returns_own_notifications(self, auth_client, user, notification):
        response = auth_client.get(BASE_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == notification.pk

    def test_does_not_return_other_users_notifications(
        self, auth_client, user, other_user
    ):
        NotificationService.create(
            recipient=other_user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Other user",
        )
        response = auth_client.get(BASE_URL)
        assert response.data["count"] == 0

    def test_unread_filter(self, auth_client, user):
        _make_notifications(user, 3)
        n_read = _make_notifications(user, 1)[0]
        NotificationService.mark_read(n_read, user)

        response = auth_client.get(f"{BASE_URL}?unread=true")
        assert response.data["count"] == 3
        ids = [r["id"] for r in response.data["results"]]
        assert n_read.pk not in ids

    def test_returns_all_without_unread_filter(self, auth_client, user):
        _make_notifications(user, 2)
        NotificationService.mark_all_read(user)
        _make_notifications(user, 2)

        response = auth_client.get(BASE_URL)
        assert response.data["count"] == 4

    def test_newest_first_ordering(self, auth_client, user):
        notifications = _make_notifications(user, 3)
        response = auth_client.get(BASE_URL)
        ids = [r["id"] for r in response.data["results"]]
        assert ids[0] == notifications[-1].pk  # newest first

    def test_response_includes_expected_fields(self, auth_client, user, notification):
        response = auth_client.get(BASE_URL)
        result = response.data["results"][0]
        assert "id" in result
        assert "notification_type" in result
        assert "notification_type_display" in result
        assert "title" in result
        assert "body" in result
        assert "is_read" in result
        assert "read_at" in result
        assert "extra_data" in result
        assert "created_at" in result


# ─── retrieve ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestNotificationRetrieve:
    def test_retrieve_own_notification(self, auth_client, user, notification):
        response = auth_client.get(detail_url(notification.pk))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == notification.pk

    def test_retrieve_other_users_notification_returns_404(
        self, auth_client, other_user
    ):
        other_notif = NotificationService.create(
            recipient=other_user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Other",
        )
        response = auth_client.get(detail_url(other_notif.pk))
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ─── mark_read ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestMarkRead:
    def test_marks_notification_as_read(self, auth_client, user, notification):
        response = auth_client.post(mark_read_url(notification.pk))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_read"] is True
        notification.refresh_from_db()
        assert notification.is_read is True

    def test_mark_read_sets_read_at(self, auth_client, user, notification):
        response = auth_client.post(mark_read_url(notification.pk))
        assert response.data["read_at"] is not None

    def test_cannot_mark_other_users_notification(self, user, other_user, notification):
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.post(mark_read_url(notification.pk))
        # notification belongs to user, not other_user → 404 from get_object()
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_mark_already_read_is_idempotent(self, auth_client, user, notification):
        auth_client.post(mark_read_url(notification.pk))
        response = auth_client.post(mark_read_url(notification.pk))
        assert response.status_code == status.HTTP_200_OK


# ─── mark_all_read ────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestMarkAllRead:
    def test_marks_all_as_read(self, auth_client, user):
        _make_notifications(user, 5)
        response = auth_client.post(MARK_ALL_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["marked_read"] == 5
        assert Notification.objects.filter(recipient=user, is_read=False).count() == 0

    def test_does_not_affect_other_users(self, auth_client, user, other_user):
        NotificationService.create(
            recipient=other_user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Other",
        )
        auth_client.post(MARK_ALL_URL)
        assert Notification.objects.filter(recipient=other_user, is_read=False).count() == 1

    def test_returns_zero_when_all_already_read(self, auth_client, user):
        _make_notifications(user, 2)
        auth_client.post(MARK_ALL_URL)
        response = auth_client.post(MARK_ALL_URL)
        assert response.data["marked_read"] == 0


# ─── unread_count ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestUnreadCount:
    def test_returns_unread_count(self, auth_client, user):
        _make_notifications(user, 3)
        response = auth_client.get(UNREAD_COUNT_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["unread_count"] == 3

    def test_count_decreases_after_mark_all_read(self, auth_client, user):
        _make_notifications(user, 3)
        auth_client.post(MARK_ALL_URL)
        response = auth_client.get(UNREAD_COUNT_URL)
        assert response.data["unread_count"] == 0

    def test_count_is_zero_with_no_notifications(self, auth_client):
        response = auth_client.get(UNREAD_COUNT_URL)
        assert response.data["unread_count"] == 0

    def test_excludes_other_users(self, auth_client, user, other_user):
        NotificationService.create(
            recipient=other_user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Other",
        )
        response = auth_client.get(UNREAD_COUNT_URL)
        assert response.data["unread_count"] == 0
