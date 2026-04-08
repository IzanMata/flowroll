"""Tests for the Notification model."""

import pytest
from django.utils import timezone

from factories import UserFactory
from notifications.models import CHECKIN_MILESTONES, Notification


@pytest.mark.django_db
class TestNotificationModel:
    def test_str_contains_type_and_title(self):
        user = UserFactory()
        n = Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Blue Belt — Promoted!",
        )
        s = str(n)
        assert "BELT_PROMOTION" in s
        assert "Blue Belt" in s

    def test_default_is_read_is_false(self):
        user = UserFactory()
        n = Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.GENERAL if hasattr(
                Notification.NotificationType, "GENERAL"
            ) else Notification.NotificationType.BELT_PROMOTION,
            title="Test",
        )
        assert n.is_read is False

    def test_default_read_at_is_none(self):
        user = UserFactory()
        n = Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Test",
        )
        assert n.read_at is None

    def test_default_extra_data_is_empty_dict(self):
        user = UserFactory()
        n = Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Test",
        )
        assert n.extra_data == {}

    def test_mark_as_read_sets_fields(self):
        user = UserFactory()
        n = Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Test",
        )
        before = timezone.now()
        n.mark_as_read()
        assert n.is_read is True
        assert n.read_at is not None
        assert n.read_at >= before

    def test_mark_as_read_does_not_save(self):
        user = UserFactory()
        n = Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Test",
        )
        n.mark_as_read()
        n_fresh = Notification.objects.get(pk=n.pk)
        assert n_fresh.is_read is False  # not saved to DB

    def test_ordering_newest_first(self):
        user = UserFactory()
        n1 = Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="First",
        )
        n2 = Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.CHECKIN_MILESTONE,
            title="Second",
        )
        ids = list(Notification.objects.filter(recipient=user).values_list("pk", flat=True))
        assert ids[0] == n2.pk  # newest first

    def test_extra_data_stored_and_retrieved(self):
        user = UserFactory()
        data = {"athlete_id": 42, "belt": "blue"}
        n = Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Test",
            extra_data=data,
        )
        n.refresh_from_db()
        assert n.extra_data == data

    def test_checkin_milestones_are_defined(self):
        assert 10 in CHECKIN_MILESTONES
        assert 50 in CHECKIN_MILESTONES
        assert 100 in CHECKIN_MILESTONES
        assert 5 not in CHECKIN_MILESTONES
