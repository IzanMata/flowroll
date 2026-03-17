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

        P2 fix: pre-compute all metrics once before the loop to avoid
        N*M queries (was: up to 3 DB hits per achievement × N achievements).
        """
        already_earned_ids = set(
            AthleteAchievement.objects.filter(athlete=athlete).values_list(
                "achievement_id", flat=True
            )
        )

        # Compute expensive metrics once; pass into _is_triggered
        checkin_count = athlete.check_ins.count()
        current_streak = StatsAggregationService.compute_current_streak(athlete)

        newly_awarded = []

        auto_achievements = Achievement.objects.exclude(
            trigger_type=Achievement.TriggerType.MANUAL
        ).exclude(pk__in=already_earned_ids)

        for achievement in auto_achievements:
            if AchievementService._is_triggered(
                athlete, achievement, checkin_count=checkin_count, current_streak=current_streak
            ):
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
    def _is_triggered(
        athlete: AthleteProfile,
        achievement: Achievement,
        *,
        checkin_count: int,
        current_streak: int,
    ) -> bool:
        threshold = achievement.trigger_value or 0
        if achievement.trigger_type == Achievement.TriggerType.CHECKIN_COUNT:
            return checkin_count >= threshold
        if achievement.trigger_type == Achievement.TriggerType.MAT_HOURS:
            return athlete.mat_hours >= threshold
        if achievement.trigger_type == Achievement.TriggerType.STREAK_DAYS:
            return current_streak >= threshold
        return False


class StatsAggregationService:
    """Computes training stats for the Strava-style athlete profile."""

    @staticmethod
    def compute_current_streak(athlete: AthleteProfile) -> int:
        """
        Return the current number of consecutive calendar days with at least one check-in.

        P3 fix: load only distinct dates in reverse-chronological order and stop
        as soon as a gap is found, instead of fetching ALL historical dates into memory.
        """
        from datetime import date, timedelta

        today = date.today()
        streak = 0
        expected = today

        dates_desc = (
            athlete.check_ins
            .values_list("training_class__scheduled_at__date", flat=True)
            .order_by("-training_class__scheduled_at__date")
            .distinct()
        )

        for checkin_date in dates_desc:
            if checkin_date == expected:
                streak += 1
                expected -= timedelta(days=1)
            elif checkin_date < expected:
                # Gap found — streak is broken
                break

        return streak

    @staticmethod
    def get_summary(athlete: AthleteProfile) -> dict:
        """Return a stats dictionary for the athlete profile page.

        P4 fix: collapse total_check_ins and achievements_count into a single
        aggregate() call to avoid 2 extra sequential COUNT queries.
        """
        from django.db.models import Count

        agg = athlete.check_ins.aggregate(total=Count("id"))
        total_check_ins = agg["total"]

        achievements_count = athlete.achievements.count()

        return {
            "total_check_ins": total_check_ins,
            "mat_hours": athlete.mat_hours,
            "current_streak_days": StatsAggregationService.compute_current_streak(athlete),
            "achievements_count": achievements_count,
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
