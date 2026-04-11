"""
Notification model — in-app notification inbox for athletes.

Notifications are created synchronously inside service calls so they
are always consistent with DB state. The `extra_data` JSONField stores
entity references (class_id, belt, etc.) for deep-linking in the client.
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from core.mixins import TimestampMixin

# Check-in counts that trigger a milestone notification.
CHECKIN_MILESTONES = {10, 25, 50, 100, 200, 500}


class Notification(TimestampMixin, models.Model):
    class NotificationType(models.TextChoices):
        CHECKIN_MILESTONE = "CHECKIN_MILESTONE", "Check-in Milestone"
        BELT_PROMOTION = "BELT_PROMOTION", "Belt Promotion"
        STRIPE_AWARD = "STRIPE_AWARD", "Stripe Awarded"
        ACHIEVEMENT_UNLOCKED = "ACHIEVEMENT_UNLOCKED", "Achievement Unlocked"
        CLASS_REMINDER = "CLASS_REMINDER", "Class Reminder"
        PAYMENT_SUCCEEDED = "PAYMENT_SUCCEEDED", "Payment Succeeded"
        PAYMENT_FAILED = "PAYMENT_FAILED", "Payment Failed"
        PROMOTION_READY = "PROMOTION_READY", "Promotion Ready"

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    # Stores entity references for client deep-links (e.g. {"class_id": 42}).
    extra_data = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["recipient", "created_at"]),
        ]

    def __str__(self):
        return f"[{self.notification_type}] → {self.recipient_id}: {self.title}"

    def mark_as_read(self) -> None:
        """Mark this notification as read in-place (does not save)."""
        self.is_read = True
        self.read_at = timezone.now()
