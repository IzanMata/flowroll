"""
Achievement evaluation and stats aggregation services.
"""
from __future__ import annotations

from typing import List

from django.db import transaction

from athletes.models import AthleteProfile

from .models import Achievement, AthleteAchievement, OpenMatRSVP, OpenMatSession


class AchievementService:
    """Evaluates and awards achievements based on athlete stats."""

    @staticmethod
    @transaction.atomic
    def evaluate_and_award(athlete: AthleteProfile) -> List[AthleteAchievement]:
        """
        Check all automatic achievements and award any newly earned ones.
        Returns the list of newly created AthleteAchievement records.
        """
        already_earned_ids = set(
            AthleteAchievement.objects.filter(athlete=athlete).values_list(
                "achievement_id", flat=True
            )
        )
        newly_awarded = []

        auto_achievements = Achievement.objects.exclude(
            trigger_type=Achievement.TriggerType.MANUAL
        ).exclude(pk__in=already_earned_ids)

        for achievement in auto_achievements:
            if AchievementService._is_triggered(athlete, achievement):
                earned = AthleteAchievement.objects.create(
                    athlete=athlete, achievement=achievement
                )
                newly_awarded.append(earned)

        return newly_awarded

    @staticmethod
    def award_manual(
        athlete: AthleteProfile,
        achievement: Achievement,
        awarded_by: AthleteProfile,
    ) -> AthleteAchievement:
        """Professor manually awards a badge to an athlete."""
        if achievement.trigger_type != Achievement.TriggerType.MANUAL:
            raise ValueError("This achievement is not manually awardable.")
        earned, created = AthleteAchievement.objects.get_or_create(
            athlete=athlete,
            achievement=achievement,
            defaults={"awarded_by": awarded_by},
        )
        if not created:
            raise ValueError(f"{athlete} has already earned '{achievement}'.")
        return earned

    @staticmethod
    def _is_triggered(athlete: AthleteProfile, achievement: Achievement) -> bool:
        threshold = achievement.trigger_value or 0
        if achievement.trigger_type == Achievement.TriggerType.CHECKIN_COUNT:
            count = athlete.check_ins.count()
            return count >= threshold
        if achievement.trigger_type == Achievement.TriggerType.MAT_HOURS:
            return athlete.mat_hours >= threshold
        if achievement.trigger_type == Achievement.TriggerType.STREAK_DAYS:
            streak = StatsAggregationService.compute_current_streak(athlete)
            return streak >= threshold
        return False


class StatsAggregationService:
    """Computes training stats for the Strava-style athlete profile."""

    @staticmethod
    def compute_current_streak(athlete: AthleteProfile) -> int:
        """
        Return the current number of consecutive calendar days with at least one check-in.
        """
        from datetime import date, timedelta

        check_in_dates = set(
            athlete.check_ins.values_list(
                "training_class__scheduled_at__date", flat=True
            )
        )
        if not check_in_dates:
            return 0

        streak = 0
        current = date.today()
        while current in check_in_dates:
            streak += 1
            current -= timedelta(days=1)
        return streak

    @staticmethod
    def get_summary(athlete: AthleteProfile) -> dict:
        """Return a stats dictionary for the athlete profile page."""
        total_check_ins = athlete.check_ins.count()
        return {
            "total_check_ins": total_check_ins,
            "mat_hours": athlete.mat_hours,
            "current_streak_days": StatsAggregationService.compute_current_streak(athlete),
            "achievements_count": athlete.achievements.count(),
        }


class OpenMatService:
    @staticmethod
    @transaction.atomic
    def rsvp(athlete: AthleteProfile, session: OpenMatSession, rsvp_status: str) -> OpenMatRSVP:
        rsvp, _ = OpenMatRSVP.objects.update_or_create(
            session=session,
            athlete=athlete,
            defaults={"status": rsvp_status},
        )
        return rsvp
