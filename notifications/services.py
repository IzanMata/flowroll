"""
Notification services.

NotificationService  — low-level create / read / bulk-read helpers.
NotificationTriggers — domain-specific factory methods called by other services.

Triggers are called synchronously at the end of the originating transaction
so the notification is always written atomically with the event that caused it.
All cross-app model imports are lazy (inside the method) to prevent circular
import issues.
"""

from __future__ import annotations

from typing import Optional

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .models import CHECKIN_MILESTONES, Notification


class NotificationService:
    """Low-level helpers for creating and managing Notification records."""

    @staticmethod
    def create(
        recipient: User,
        notification_type: str,
        title: str,
        body: str = "",
        extra_data: Optional[dict] = None,
    ) -> Notification:
        """Create and persist a Notification. Always returns the new record."""
        return Notification.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            body=body,
            extra_data=extra_data or {},
        )

    @staticmethod
    def create_if_not_exists(
        recipient: User,
        notification_type: str,
        dedup_key: str,
        title: str,
        body: str = "",
        extra_data: Optional[dict] = None,
    ) -> Optional[Notification]:
        """
        Create a notification only if one with the same dedup_key does not
        already exist for this recipient+type. Returns None on duplicate.

        `dedup_key` is stored as extra_data["_dedup_key"] and used to prevent
        sending the same notification twice (e.g. class reminder).
        """
        merged_data = {**(extra_data or {}), "_dedup_key": dedup_key}
        exists = Notification.objects.filter(
            recipient=recipient,
            notification_type=notification_type,
            extra_data___dedup_key=dedup_key,
        ).exists()
        if exists:
            return None
        return Notification.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            body=body,
            extra_data=merged_data,
        )

    @staticmethod
    @transaction.atomic
    def mark_read(notification: Notification, user: User) -> Notification:
        """Mark a single notification as read. Raises ValueError if not the owner."""
        if notification.recipient_id != user.pk:
            raise ValueError("Cannot mark another user's notification as read.")
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at"])
        return notification

    @staticmethod
    @transaction.atomic
    def mark_all_read(user: User) -> int:
        """Mark all unread notifications for a user as read. Returns count updated."""
        now = timezone.now()
        return Notification.objects.filter(
            recipient=user,
            is_read=False,
        ).update(is_read=True, read_at=now)

    @staticmethod
    def unread_count(user: User) -> int:
        return Notification.objects.filter(recipient=user, is_read=False).count()


class NotificationTriggers:
    """
    Domain-specific notification factories. Each method is called from the
    corresponding service after its primary DB operation succeeds.

    All methods are safe to call inside an open transaction — they simply
    create a Notification row. Any failure is propagated to the caller.
    """

    @staticmethod
    def on_checkin(athlete, total_checkins: int) -> Optional[Notification]:
        """
        Fire a CHECKIN_MILESTONE notification if the new total_checkins
        value lands exactly on a milestone number.
        """
        if total_checkins not in CHECKIN_MILESTONES:
            return None
        return NotificationService.create(
            recipient=athlete.user,
            notification_type=Notification.NotificationType.CHECKIN_MILESTONE,
            title=f"🏅 {total_checkins} check-ins!",
            body=(
                f"Congratulations! You've reached {total_checkins} check-ins. "
                "Keep showing up!"
            ),
            extra_data={"total_checkins": total_checkins},
        )

    @staticmethod
    def on_belt_promotion(athlete, new_belt: str) -> Notification:
        """Notify an athlete that they've been promoted to a new belt."""
        belt_display = new_belt.capitalize()
        return NotificationService.create(
            recipient=athlete.user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title=f"🥋 {belt_display} Belt — Promoted!",
            body=(
                f"Congratulations! You've been promoted to {belt_display} belt. "
                "Your hard work has paid off!"
            ),
            extra_data={"new_belt": new_belt, "athlete_id": athlete.pk},
        )

    @staticmethod
    def on_stripe_award(athlete, stripes: int) -> Notification:
        """Notify an athlete that they've received a new stripe."""
        return NotificationService.create(
            recipient=athlete.user,
            notification_type=Notification.NotificationType.STRIPE_AWARD,
            title=f"⭐ Stripe #{stripes} awarded!",
            body=(
                f"You've earned stripe #{stripes} on your {athlete.belt.capitalize()} belt. "
                "Keep training!"
            ),
            extra_data={"stripes": stripes, "belt": athlete.belt, "athlete_id": athlete.pk},
        )

    @staticmethod
    def on_achievement_unlocked(athlete_achievement) -> Notification:
        """Notify an athlete that they've unlocked an achievement."""
        achievement = athlete_achievement.achievement
        return NotificationService.create(
            recipient=athlete_achievement.athlete.user,
            notification_type=Notification.NotificationType.ACHIEVEMENT_UNLOCKED,
            title=f"🏆 Achievement unlocked: {achievement.name}",
            body=achievement.description,
            extra_data={
                "achievement_id": achievement.pk,
                "achievement_name": achievement.name,
                "athlete_id": athlete_achievement.athlete.pk,
            },
        )

    @staticmethod
    def on_payment_succeeded(payment) -> Notification:
        """Notify the athlete that their payment was successful."""
        return NotificationService.create(
            recipient=payment.athlete.user,
            notification_type=Notification.NotificationType.PAYMENT_SUCCEEDED,
            title="✅ Payment confirmed",
            body=(
                f"Your payment of {payment.amount_paid} {payment.currency.upper()} "
                "was processed successfully."
            ),
            extra_data={
                "payment_id": payment.pk,
                "amount_paid": str(payment.amount_paid),
                "currency": payment.currency,
                "payment_type": payment.payment_type,
            },
        )

    @staticmethod
    def on_payment_failed(athlete_user: User, amount_cents: int, currency: str) -> Notification:
        """Notify the athlete that their payment failed."""
        amount = amount_cents / 100
        return NotificationService.create(
            recipient=athlete_user,
            notification_type=Notification.NotificationType.PAYMENT_FAILED,
            title="❌ Payment failed",
            body=(
                f"Your payment of {amount:.2f} {currency.upper()} could not be processed. "
                "Please update your payment method."
            ),
            extra_data={"amount_cents": amount_cents, "currency": currency},
        )

    @staticmethod
    def on_class_reminder(recipient: User, training_class) -> Optional[Notification]:
        """
        Send a class reminder to a single recipient, deduplicating by class id.
        Returns None if a reminder was already sent for this class+recipient.
        """
        dedup_key = f"class_reminder_{training_class.pk}"
        scheduled = training_class.scheduled_at.strftime("%A %d %b at %H:%M")
        return NotificationService.create_if_not_exists(
            recipient=recipient,
            notification_type=Notification.NotificationType.CLASS_REMINDER,
            dedup_key=dedup_key,
            title=f"📅 Reminder: {training_class.title}",
            body=f"You have a class scheduled {scheduled}. Don't forget to show up!",
            extra_data={
                "training_class_id": training_class.pk,
                "scheduled_at": training_class.scheduled_at.isoformat(),
            },
        )
