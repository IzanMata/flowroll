"""
Tests for the send_class_reminders Celery task.

All tests call the task function directly (no worker) and mock nothing
— the task writes Notification rows to the DB, which we assert on.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    TrainingClassFactory,
    UserFactory,
)
from notifications.models import Notification
from notifications.tasks import send_class_reminders


@pytest.mark.django_db
class TestSendClassReminders:
    def _make_member(self, academy):
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        return user

    def test_sends_reminder_for_class_in_window(self):
        academy = AcademyFactory()
        member = self._make_member(academy)
        # Scheduled 24 hours from now — inside the 1h-25h window
        TrainingClassFactory(
            academy=academy,
            scheduled_at=timezone.now() + timedelta(hours=24),
        )
        result = send_class_reminders()
        assert result["sent"] == 1
        assert Notification.objects.filter(
            recipient=member,
            notification_type=Notification.NotificationType.CLASS_REMINDER,
        ).count() == 1

    def test_skips_class_starting_within_one_hour(self):
        academy = AcademyFactory()
        self._make_member(academy)
        TrainingClassFactory(
            academy=academy,
            scheduled_at=timezone.now() + timedelta(minutes=30),
        )
        result = send_class_reminders()
        assert result["sent"] == 0

    def test_skips_class_more_than_25_hours_away(self):
        academy = AcademyFactory()
        self._make_member(academy)
        TrainingClassFactory(
            academy=academy,
            scheduled_at=timezone.now() + timedelta(hours=26),
        )
        result = send_class_reminders()
        assert result["sent"] == 0

    def test_sends_to_all_active_members(self):
        academy = AcademyFactory()
        m1 = self._make_member(academy)
        m2 = self._make_member(academy)
        TrainingClassFactory(
            academy=academy,
            scheduled_at=timezone.now() + timedelta(hours=20),
        )
        result = send_class_reminders()
        assert result["sent"] == 2
        assert Notification.objects.filter(
            recipient=m1,
            notification_type=Notification.NotificationType.CLASS_REMINDER,
        ).exists()
        assert Notification.objects.filter(
            recipient=m2,
            notification_type=Notification.NotificationType.CLASS_REMINDER,
        ).exists()

    def test_skips_inactive_members(self):
        academy = AcademyFactory()
        inactive_user = UserFactory()
        AcademyMembershipFactory(
            user=inactive_user, academy=academy, role="STUDENT", is_active=False
        )
        TrainingClassFactory(
            academy=academy,
            scheduled_at=timezone.now() + timedelta(hours=20),
        )
        result = send_class_reminders()
        assert result["sent"] == 0

    def test_deduplicates_on_repeated_run(self):
        academy = AcademyFactory()
        member = self._make_member(academy)
        TrainingClassFactory(
            academy=academy,
            scheduled_at=timezone.now() + timedelta(hours=20),
        )
        send_class_reminders()
        result = send_class_reminders()  # run again
        assert result["sent"] == 0  # deduped
        assert Notification.objects.filter(
            recipient=member,
            notification_type=Notification.NotificationType.CLASS_REMINDER,
        ).count() == 1

    def test_handles_no_classes(self):
        result = send_class_reminders()
        assert result["sent"] == 0

    def test_multiple_classes_multiple_members(self):
        academy = AcademyFactory()
        m1 = self._make_member(academy)
        m2 = self._make_member(academy)
        TrainingClassFactory(academy=academy, scheduled_at=timezone.now() + timedelta(hours=10))
        TrainingClassFactory(academy=academy, scheduled_at=timezone.now() + timedelta(hours=20))
        result = send_class_reminders()
        assert result["sent"] == 4  # 2 classes × 2 members
