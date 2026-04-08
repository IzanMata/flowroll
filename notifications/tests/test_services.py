"""
Tests for NotificationService and NotificationTriggers.

Also covers trigger integration with CheckInService, AthleteProfileService,
AchievementService, and payment webhook handlers.
"""

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    TrainingClassFactory,
    UserFactory,
)
from notifications.models import Notification
from notifications.services import NotificationService, NotificationTriggers


# ─── NotificationService.create ───────────────────────────────────────────────


@pytest.mark.django_db
class TestNotificationServiceCreate:
    def test_creates_notification(self):
        user = UserFactory()
        n = NotificationService.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Blue Belt!",
            body="Congrats!",
        )
        assert n.pk is not None
        assert n.recipient == user
        assert n.title == "Blue Belt!"
        assert n.is_read is False

    def test_stores_extra_data(self):
        user = UserFactory()
        n = NotificationService.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Test",
            extra_data={"belt": "blue"},
        )
        assert n.extra_data["belt"] == "blue"

    def test_empty_extra_data_by_default(self):
        user = UserFactory()
        n = NotificationService.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Test",
        )
        assert n.extra_data == {}


# ─── NotificationService.create_if_not_exists ─────────────────────────────────


@pytest.mark.django_db
class TestCreateIfNotExists:
    def test_creates_on_first_call(self):
        user = UserFactory()
        n = NotificationService.create_if_not_exists(
            recipient=user,
            notification_type=Notification.NotificationType.CLASS_REMINDER,
            dedup_key="class_42",
            title="Class Reminder",
        )
        assert n is not None
        assert n.pk is not None

    def test_returns_none_on_duplicate(self):
        user = UserFactory()
        NotificationService.create_if_not_exists(
            recipient=user,
            notification_type=Notification.NotificationType.CLASS_REMINDER,
            dedup_key="class_42",
            title="Class Reminder",
        )
        result = NotificationService.create_if_not_exists(
            recipient=user,
            notification_type=Notification.NotificationType.CLASS_REMINDER,
            dedup_key="class_42",
            title="Class Reminder",
        )
        assert result is None

    def test_different_dedup_key_creates_new(self):
        user = UserFactory()
        NotificationService.create_if_not_exists(
            recipient=user,
            notification_type=Notification.NotificationType.CLASS_REMINDER,
            dedup_key="class_1",
            title="Class 1 Reminder",
        )
        n2 = NotificationService.create_if_not_exists(
            recipient=user,
            notification_type=Notification.NotificationType.CLASS_REMINDER,
            dedup_key="class_2",
            title="Class 2 Reminder",
        )
        assert n2 is not None
        assert Notification.objects.filter(recipient=user).count() == 2

    def test_different_user_same_key_creates_new(self):
        user1 = UserFactory()
        user2 = UserFactory()
        NotificationService.create_if_not_exists(
            recipient=user1,
            notification_type=Notification.NotificationType.CLASS_REMINDER,
            dedup_key="class_42",
            title="Reminder",
        )
        n2 = NotificationService.create_if_not_exists(
            recipient=user2,
            notification_type=Notification.NotificationType.CLASS_REMINDER,
            dedup_key="class_42",
            title="Reminder",
        )
        assert n2 is not None


# ─── NotificationService.mark_read ────────────────────────────────────────────


@pytest.mark.django_db
class TestMarkRead:
    def test_marks_notification_as_read(self):
        user = UserFactory()
        n = NotificationService.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Test",
        )
        result = NotificationService.mark_read(n, user)
        assert result.is_read is True
        assert result.read_at is not None
        n.refresh_from_db()
        assert n.is_read is True

    def test_raises_if_not_owner(self):
        owner = UserFactory()
        other = UserFactory()
        n = NotificationService.create(
            recipient=owner,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Test",
        )
        with pytest.raises(ValueError, match="another user"):
            NotificationService.mark_read(n, other)

    def test_idempotent_already_read(self):
        user = UserFactory()
        n = NotificationService.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Test",
        )
        t = timezone.now()
        Notification.objects.filter(pk=n.pk).update(is_read=True, read_at=t)
        n.refresh_from_db()
        result = NotificationService.mark_read(n, user)
        assert result.is_read is True
        assert result.read_at == t  # unchanged


# ─── NotificationService.mark_all_read ────────────────────────────────────────


@pytest.mark.django_db
class TestMarkAllRead:
    def test_marks_all_unread_as_read(self):
        user = UserFactory()
        for _ in range(3):
            NotificationService.create(
                recipient=user,
                notification_type=Notification.NotificationType.BELT_PROMOTION,
                title="Test",
            )
        count = NotificationService.mark_all_read(user)
        assert count == 3
        assert Notification.objects.filter(recipient=user, is_read=False).count() == 0

    def test_does_not_affect_other_users(self):
        user1 = UserFactory()
        user2 = UserFactory()
        NotificationService.create(
            recipient=user2,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Other user",
        )
        NotificationService.mark_all_read(user1)
        assert Notification.objects.filter(recipient=user2, is_read=False).count() == 1

    def test_returns_zero_when_none_unread(self):
        user = UserFactory()
        count = NotificationService.mark_all_read(user)
        assert count == 0


# ─── NotificationService.unread_count ─────────────────────────────────────────


@pytest.mark.django_db
class TestUnreadCount:
    def test_counts_unread(self):
        user = UserFactory()
        for _ in range(4):
            NotificationService.create(
                recipient=user,
                notification_type=Notification.NotificationType.BELT_PROMOTION,
                title="Test",
            )
        assert NotificationService.unread_count(user) == 4

    def test_excludes_read(self):
        user = UserFactory()
        NotificationService.create(
            recipient=user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
            title="Test",
        )
        NotificationService.mark_all_read(user)
        assert NotificationService.unread_count(user) == 0


# ─── NotificationTriggers ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTriggerOnCheckin:
    def test_fires_at_milestone(self):
        athlete = AthleteProfileFactory()
        n = NotificationTriggers.on_checkin(athlete, total_checkins=10)
        assert n is not None
        assert n.notification_type == Notification.NotificationType.CHECKIN_MILESTONE
        assert "10" in n.title
        assert n.recipient == athlete.user

    def test_does_not_fire_at_non_milestone(self):
        athlete = AthleteProfileFactory()
        n = NotificationTriggers.on_checkin(athlete, total_checkins=11)
        assert n is None

    def test_fires_at_all_milestones(self):
        from notifications.models import CHECKIN_MILESTONES
        athlete = AthleteProfileFactory()
        for milestone in CHECKIN_MILESTONES:
            n = NotificationTriggers.on_checkin(athlete, total_checkins=milestone)
            assert n is not None, f"Expected notification at milestone {milestone}"


@pytest.mark.django_db
class TestTriggerOnBeltPromotion:
    def test_creates_belt_promotion_notification(self):
        athlete = AthleteProfileFactory(belt="white")
        n = NotificationTriggers.on_belt_promotion(athlete, new_belt="blue")
        assert n.notification_type == Notification.NotificationType.BELT_PROMOTION
        assert "Blue" in n.title
        assert n.recipient == athlete.user

    def test_extra_data_contains_new_belt(self):
        athlete = AthleteProfileFactory()
        n = NotificationTriggers.on_belt_promotion(athlete, new_belt="purple")
        assert n.extra_data["new_belt"] == "purple"


@pytest.mark.django_db
class TestTriggerOnStripeAward:
    def test_creates_stripe_notification(self):
        athlete = AthleteProfileFactory(belt="blue", stripes=1)
        n = NotificationTriggers.on_stripe_award(athlete, stripes=1)
        assert n.notification_type == Notification.NotificationType.STRIPE_AWARD
        assert "#1" in n.title
        assert n.recipient == athlete.user


@pytest.mark.django_db
class TestTriggerOnAchievementUnlocked:
    def test_creates_achievement_notification(self):
        from community.models import Achievement, AthleteAchievement
        athlete = AthleteProfileFactory()
        achievement = Achievement.objects.create(
            name="Mat Warrior",
            description="100 check-ins achieved",
            trigger_type="CHECKIN_COUNT",
            trigger_value=100,
        )
        aa = AthleteAchievement.objects.create(athlete=athlete, achievement=achievement)
        n = NotificationTriggers.on_achievement_unlocked(aa)
        assert n.notification_type == Notification.NotificationType.ACHIEVEMENT_UNLOCKED
        assert "Mat Warrior" in n.title
        assert n.recipient == athlete.user


@pytest.mark.django_db
class TestTriggerOnPaymentSucceeded:
    def test_creates_payment_succeeded_notification(self):
        from factories import PaymentFactory
        payment = PaymentFactory(status="SUCCEEDED")
        n = NotificationTriggers.on_payment_succeeded(payment)
        assert n.notification_type == Notification.NotificationType.PAYMENT_SUCCEEDED
        assert n.recipient == payment.athlete.user
        assert str(payment.amount_paid) in n.body


@pytest.mark.django_db
class TestTriggerOnPaymentFailed:
    def test_creates_payment_failed_notification(self):
        user = UserFactory()
        n = NotificationTriggers.on_payment_failed(
            athlete_user=user,
            amount_cents=4999,
            currency="eur",
        )
        assert n.notification_type == Notification.NotificationType.PAYMENT_FAILED
        assert n.recipient == user
        assert "49.99" in n.body


@pytest.mark.django_db
class TestTriggerOnClassReminder:
    def test_creates_class_reminder(self):
        user = UserFactory()
        training_class = TrainingClassFactory()
        n = NotificationTriggers.on_class_reminder(user, training_class)
        assert n is not None
        assert n.notification_type == Notification.NotificationType.CLASS_REMINDER
        assert training_class.title in n.title
        assert n.recipient == user

    def test_deduplicates_same_class(self):
        user = UserFactory()
        training_class = TrainingClassFactory()
        n1 = NotificationTriggers.on_class_reminder(user, training_class)
        n2 = NotificationTriggers.on_class_reminder(user, training_class)
        assert n1 is not None
        assert n2 is None
        assert Notification.objects.filter(recipient=user).count() == 1


# ─── Integration: CheckInService fires milestone trigger ──────────────────────


@pytest.mark.django_db
class TestCheckinMilestoneIntegration:
    def test_10th_checkin_creates_notification(self):
        from attendance.models import CheckIn, TrainingClass
        from attendance.services import CheckInService

        academy = AcademyFactory()
        athlete = AthleteProfileFactory(academy=academy)

        # Create 9 prior check-ins to set up the count
        for i in range(9):
            tc = TrainingClassFactory(academy=academy)
            CheckIn.objects.create(athlete=athlete, training_class=tc, method="MANUAL")

        # 10th check-in via service — should fire notification
        tc_10 = TrainingClassFactory(academy=academy)
        CheckInService.check_in_manual(athlete, tc_10)

        assert Notification.objects.filter(
            recipient=athlete.user,
            notification_type=Notification.NotificationType.CHECKIN_MILESTONE,
        ).count() == 1

    def test_non_milestone_checkin_no_notification(self):
        from attendance.services import CheckInService

        academy = AcademyFactory()
        athlete = AthleteProfileFactory(academy=academy)
        tc = TrainingClassFactory(academy=academy)
        CheckInService.check_in_manual(athlete, tc)

        assert Notification.objects.filter(
            recipient=athlete.user,
            notification_type=Notification.NotificationType.CHECKIN_MILESTONE,
        ).count() == 0


# ─── Integration: AthleteProfileService fires triggers ────────────────────────


@pytest.mark.django_db
class TestBeltPromotionIntegration:
    def test_promote_belt_creates_notification(self):
        from athletes.services import AthleteProfileService

        academy = AcademyFactory()
        professor = AthleteProfileFactory(academy=academy, role="PROFESSOR")
        AcademyMembershipFactory(
            user=professor.user, academy=academy, role="PROFESSOR", is_active=True
        )
        athlete = AthleteProfileFactory(academy=academy, belt="white")
        AcademyMembershipFactory(
            user=athlete.user, academy=academy, role="STUDENT", is_active=True
        )

        AthleteProfileService.promote_belt(athlete, "blue", professor)

        assert Notification.objects.filter(
            recipient=athlete.user,
            notification_type=Notification.NotificationType.BELT_PROMOTION,
        ).count() == 1


@pytest.mark.django_db
class TestStripeAwardIntegration:
    def test_award_stripe_creates_notification(self):
        from athletes.services import AthleteProfileService

        academy = AcademyFactory()
        professor = AthleteProfileFactory(academy=academy, role="PROFESSOR")
        AcademyMembershipFactory(
            user=professor.user, academy=academy, role="PROFESSOR", is_active=True
        )
        athlete = AthleteProfileFactory(academy=academy, belt="blue", stripes=0)
        AcademyMembershipFactory(
            user=athlete.user, academy=academy, role="STUDENT", is_active=True
        )

        AthleteProfileService.award_stripe(athlete, professor)

        assert Notification.objects.filter(
            recipient=athlete.user,
            notification_type=Notification.NotificationType.STRIPE_AWARD,
        ).count() == 1
