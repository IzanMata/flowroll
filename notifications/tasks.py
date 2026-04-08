"""
Celery tasks for the notifications app.

send_class_reminders — runs every hour via django-celery-beat.
Finds TrainingClasses scheduled in the next 25 hours (exclusive of the
next hour, to create a ~24-hour advance window) and sends a reminder to
every active member of the academy.  Deduplication is handled inside
NotificationTriggers.on_class_reminder via the _dedup_key mechanism, so
re-running the task is always safe.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="notifications.send_class_reminders")
def send_class_reminders() -> dict:
    """
    Send 24-hour advance reminders for upcoming training classes.

    Window: now+1h … now+25h  (catches classes in the next 24 hours,
    but not those starting within the next hour, which is too late for
    a useful reminder).

    Returns a summary dict with the count of notifications sent.
    """
    from datetime import timedelta

    from core.models import AcademyMembership
    from attendance.models import TrainingClass
    from .services import NotificationTriggers

    now = timezone.now()
    window_start = now + timedelta(hours=1)
    window_end = now + timedelta(hours=25)

    classes = (
        TrainingClass.objects.filter(
            scheduled_at__gte=window_start,
            scheduled_at__lt=window_end,
        )
        .select_related("academy")
    )

    sent_count = 0
    for training_class in classes:
        # Find all active members of this academy
        members = AcademyMembership.objects.filter(
            academy=training_class.academy,
            is_active=True,
        ).select_related("user")

        for membership in members:
            notif = NotificationTriggers.on_class_reminder(
                recipient=membership.user,
                training_class=training_class,
            )
            if notif is not None:
                sent_count += 1

    logger.info("send_class_reminders: sent %d notifications", sent_count)
    return {"sent": sent_count}
