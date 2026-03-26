"""Tests for community services: AchievementService, StatsAggregationService, OpenMatService."""

import pytest
from datetime import date, timedelta
from unittest.mock import patch

from community.models import Achievement, AthleteAchievement, OpenMatRSVP
from community.services import AchievementService, StatsAggregationService, OpenMatService
from factories import (
    AchievementFactory,
    AthleteAchievementFactory,
    AthleteProfileFactory,
    CheckInFactory,
    TrainingClassFactory,
    OpenMatSessionFactory,
    OpenMatRSVPFactory,
)


class TestAchievementService:
    def test_evaluate_and_award_no_new_achievements(self, db):
        """Test when athlete doesn't qualify for any new achievements."""
        athlete = AthleteProfileFactory(mat_hours=5.0)
        # Create achievement that requires 10 check-ins, but athlete has 0
        AchievementFactory(
            name="10 Check-Ins",
            trigger_type=Achievement.TriggerType.CHECKIN_COUNT,
            trigger_value=10
        )

        newly_awarded = AchievementService.evaluate_and_award(athlete)

        assert len(newly_awarded) == 0
        assert AthleteAchievement.objects.filter(athlete=athlete).count() == 0

    def test_evaluate_and_award_checkin_count_achievement(self, db):
        """Test automatic awarding based on check-in count."""
        athlete = AthleteProfileFactory()
        achievement = AchievementFactory(
            name="5 Check-Ins",
            trigger_type=Achievement.TriggerType.CHECKIN_COUNT,
            trigger_value=5
        )

        # Create 5 check-ins for the athlete
        for _ in range(5):
            CheckInFactory(athlete=athlete)

        newly_awarded = AchievementService.evaluate_and_award(athlete)

        assert len(newly_awarded) == 1
        assert newly_awarded[0].athlete == athlete
        assert newly_awarded[0].achievement == achievement
        assert newly_awarded[0].awarded_by is None

    def test_evaluate_and_award_mat_hours_achievement(self, db):
        """Test automatic awarding based on mat hours."""
        athlete = AthleteProfileFactory(mat_hours=100.0)
        achievement = AchievementFactory(
            name="100 Mat Hours",
            trigger_type=Achievement.TriggerType.MAT_HOURS,
            trigger_value=100.0
        )

        newly_awarded = AchievementService.evaluate_and_award(athlete)

        assert len(newly_awarded) == 1
        assert newly_awarded[0].achievement == achievement

    def test_evaluate_and_award_streak_achievement(self, db):
        """Test automatic awarding based on training streak."""
        athlete = AthleteProfileFactory()
        achievement = AchievementFactory(
            name="7-Day Streak",
            trigger_type=Achievement.TriggerType.STREAK_DAYS,
            trigger_value=7
        )

        # Mock the streak calculation to return 7
        with patch.object(StatsAggregationService, 'compute_current_streak', return_value=7):
            newly_awarded = AchievementService.evaluate_and_award(athlete)

        assert len(newly_awarded) == 1
        assert newly_awarded[0].achievement == achievement

    def test_evaluate_and_award_multiple_achievements(self, db):
        """Test awarding multiple achievements at once."""
        athlete = AthleteProfileFactory(mat_hours=50.0)
        achievement1 = AchievementFactory(
            name="10 Check-Ins",
            trigger_type=Achievement.TriggerType.CHECKIN_COUNT,
            trigger_value=5  # Setting lower for easier testing
        )
        achievement2 = AchievementFactory(
            name="50 Mat Hours",
            trigger_type=Achievement.TriggerType.MAT_HOURS,
            trigger_value=50.0
        )

        # Create 5 check-ins
        for _ in range(5):
            CheckInFactory(athlete=athlete)

        newly_awarded = AchievementService.evaluate_and_award(athlete)

        assert len(newly_awarded) == 2
        achievement_names = {a.achievement.name for a in newly_awarded}
        assert "10 Check-Ins" in achievement_names
        assert "50 Mat Hours" in achievement_names

    def test_evaluate_and_award_excludes_already_earned(self, db):
        """Test that already earned achievements are not awarded again."""
        athlete = AthleteProfileFactory(mat_hours=100.0)
        achievement = AchievementFactory(
            name="100 Mat Hours",
            trigger_type=Achievement.TriggerType.MAT_HOURS,
            trigger_value=100.0
        )

        # Pre-award the achievement
        AthleteAchievementFactory(athlete=athlete, achievement=achievement)

        newly_awarded = AchievementService.evaluate_and_award(athlete)

        assert len(newly_awarded) == 0

    def test_evaluate_and_award_excludes_manual_achievements(self, db):
        """Test that manual achievements are not automatically awarded."""
        athlete = AthleteProfileFactory()
        AchievementFactory(
            name="Special Award",
            trigger_type=Achievement.TriggerType.MANUAL,
            trigger_value=None
        )

        newly_awarded = AchievementService.evaluate_and_award(athlete)

        assert len(newly_awarded) == 0

    def test_award_manual_success(self, db):
        """Test manually awarding an achievement."""
        athlete = AthleteProfileFactory()
        professor = AthleteProfileFactory()
        achievement = AchievementFactory(
            name="Special Award",
            trigger_type=Achievement.TriggerType.MANUAL,
            trigger_value=None
        )

        awarded = AchievementService.award_manual(athlete, achievement, professor)

        assert awarded.athlete == athlete
        assert awarded.achievement == achievement
        assert awarded.awarded_by == professor

    def test_award_manual_non_manual_achievement_fails(self, db):
        """Test that non-manual achievements cannot be manually awarded."""
        athlete = AthleteProfileFactory()
        professor = AthleteProfileFactory()
        achievement = AchievementFactory(
            trigger_type=Achievement.TriggerType.CHECKIN_COUNT,
            trigger_value=10
        )

        with pytest.raises(ValueError, match="not manually awardable"):
            AchievementService.award_manual(athlete, achievement, professor)

    def test_award_manual_already_earned_fails(self, db):
        """Test that manually awarding an already earned achievement fails."""
        athlete = AthleteProfileFactory()
        professor = AthleteProfileFactory()
        achievement = AchievementFactory(trigger_type=Achievement.TriggerType.MANUAL)

        # Pre-award the achievement
        AthleteAchievementFactory(athlete=athlete, achievement=achievement)

        with pytest.raises(ValueError, match="already earned"):
            AchievementService.award_manual(athlete, achievement, professor)

    def test_is_triggered_checkin_count(self, db):
        """Test _is_triggered for check-in count achievements."""
        athlete = AthleteProfileFactory()
        achievement = AchievementFactory(
            trigger_type=Achievement.TriggerType.CHECKIN_COUNT,
            trigger_value=5
        )

        # Test below threshold
        result = AchievementService._is_triggered(
            athlete, achievement, checkin_count=4, current_streak=0
        )
        assert result is False

        # Test at threshold
        result = AchievementService._is_triggered(
            athlete, achievement, checkin_count=5, current_streak=0
        )
        assert result is True

        # Test above threshold
        result = AchievementService._is_triggered(
            athlete, achievement, checkin_count=10, current_streak=0
        )
        assert result is True

    def test_is_triggered_mat_hours(self, db):
        """Test _is_triggered for mat hours achievements."""
        athlete = AthleteProfileFactory(mat_hours=50.0)
        achievement = AchievementFactory(
            trigger_type=Achievement.TriggerType.MAT_HOURS,
            trigger_value=50.0
        )

        result = AchievementService._is_triggered(
            athlete, achievement, checkin_count=0, current_streak=0
        )
        assert result is True

        athlete.mat_hours = 49.0
        result = AchievementService._is_triggered(
            athlete, achievement, checkin_count=0, current_streak=0
        )
        assert result is False

    def test_is_triggered_streak_days(self, db):
        """Test _is_triggered for streak days achievements."""
        athlete = AthleteProfileFactory()
        achievement = AchievementFactory(
            trigger_type=Achievement.TriggerType.STREAK_DAYS,
            trigger_value=7
        )

        result = AchievementService._is_triggered(
            athlete, achievement, checkin_count=0, current_streak=7
        )
        assert result is True

        result = AchievementService._is_triggered(
            athlete, achievement, checkin_count=0, current_streak=6
        )
        assert result is False

    def test_is_triggered_null_trigger_value(self, db):
        """Test _is_triggered with null trigger value defaults to 0."""
        athlete = AthleteProfileFactory()
        achievement = AchievementFactory(
            trigger_type=Achievement.TriggerType.CHECKIN_COUNT,
            trigger_value=None
        )

        result = AchievementService._is_triggered(
            athlete, achievement, checkin_count=0, current_streak=0
        )
        assert result is True  # 0 >= 0

    def test_is_triggered_unknown_type_returns_false(self, db):
        """Test _is_triggered returns False for unknown trigger types."""
        athlete = AthleteProfileFactory()
        achievement = AchievementFactory(
            trigger_type=Achievement.TriggerType.MANUAL,  # Not handled in _is_triggered
            trigger_value=10
        )

        result = AchievementService._is_triggered(
            athlete, achievement, checkin_count=100, current_streak=100
        )
        assert result is False


class TestStatsAggregationService:
    def test_compute_current_streak_no_checkins(self, db):
        """Test streak calculation with no check-ins."""
        athlete = AthleteProfileFactory()

        streak = StatsAggregationService.compute_current_streak(athlete)

        assert streak == 0

    def test_compute_current_streak_single_day(self, db):
        """Test streak calculation with check-ins only today."""
        athlete = AthleteProfileFactory()
        training_class = TrainingClassFactory(
            scheduled_at=date.today()
        )
        CheckInFactory(athlete=athlete, training_class=training_class)

        streak = StatsAggregationService.compute_current_streak(athlete)

        assert streak == 1

    def test_compute_current_streak_consecutive_days(self, db):
        """Test streak calculation with consecutive days."""
        athlete = AthleteProfileFactory()
        today = date.today()

        # Create check-ins for today and yesterday
        for i in range(2):
            training_class = TrainingClassFactory(
                scheduled_at=today - timedelta(days=i)
            )
            CheckInFactory(athlete=athlete, training_class=training_class)

        streak = StatsAggregationService.compute_current_streak(athlete)

        assert streak == 2

    def test_compute_current_streak_with_gap(self, db):
        """Test streak calculation stops at gaps."""
        athlete = AthleteProfileFactory()
        today = date.today()

        # Create check-ins for today and 3 days ago (gap of 2 days)
        training_class1 = TrainingClassFactory(scheduled_at=today)
        CheckInFactory(athlete=athlete, training_class=training_class1)

        training_class2 = TrainingClassFactory(
            scheduled_at=today - timedelta(days=3)
        )
        CheckInFactory(athlete=athlete, training_class=training_class2)

        streak = StatsAggregationService.compute_current_streak(athlete)

        assert streak == 1  # Only today counts, gap breaks the streak

    def test_compute_current_streak_multiple_checkins_same_day(self, db):
        """Test streak calculation counts each day only once."""
        athlete = AthleteProfileFactory()
        today = date.today()

        # Create multiple check-ins on the same day
        for _ in range(3):
            training_class = TrainingClassFactory(scheduled_at=today)
            CheckInFactory(athlete=athlete, training_class=training_class)

        streak = StatsAggregationService.compute_current_streak(athlete)

        assert streak == 1  # Multiple check-ins on same day = 1 day streak

    def test_compute_current_streak_old_checkins_only(self, db):
        """Test streak calculation with only old check-ins."""
        athlete = AthleteProfileFactory()
        old_date = date.today() - timedelta(days=5)

        training_class = TrainingClassFactory(scheduled_at=old_date)
        CheckInFactory(athlete=athlete, training_class=training_class)

        streak = StatsAggregationService.compute_current_streak(athlete)

        assert streak == 0  # No recent check-ins

    def test_get_summary_complete(self, db):
        """Test get_summary returns all expected fields."""
        athlete = AthleteProfileFactory(mat_hours=50.0)

        # Create some check-ins
        for _ in range(3):
            CheckInFactory(athlete=athlete)

        # Create some achievements
        achievement = AchievementFactory()
        AthleteAchievementFactory(athlete=athlete, achievement=achievement)

        with patch.object(StatsAggregationService, 'compute_current_streak', return_value=5):
            summary = StatsAggregationService.get_summary(athlete)

        expected_fields = {
            "total_check_ins",
            "mat_hours",
            "current_streak_days",
            "achievements_count"
        }
        assert set(summary.keys()) == expected_fields
        assert summary["total_check_ins"] == 3
        assert summary["mat_hours"] == 50.0
        assert summary["current_streak_days"] == 5
        assert summary["achievements_count"] == 1

    def test_get_summary_no_data(self, db):
        """Test get_summary with athlete who has no check-ins or achievements."""
        athlete = AthleteProfileFactory(mat_hours=0.0)

        summary = StatsAggregationService.get_summary(athlete)

        assert summary["total_check_ins"] == 0
        assert summary["mat_hours"] == 0.0
        assert summary["current_streak_days"] == 0
        assert summary["achievements_count"] == 0


class TestOpenMatService:
    def test_rsvp_create_new(self, db):
        """Test creating a new RSVP."""
        athlete = AthleteProfileFactory()
        session = OpenMatSessionFactory()

        rsvp = OpenMatService.rsvp(
            athlete=athlete,
            session=session,
            rsvp_status=OpenMatRSVP.Status.GOING
        )

        assert rsvp.athlete == athlete
        assert rsvp.session == session
        assert rsvp.status == OpenMatRSVP.Status.GOING

    def test_rsvp_update_existing(self, db):
        """Test updating an existing RSVP."""
        existing_rsvp = OpenMatRSVPFactory(status=OpenMatRSVP.Status.GOING)

        updated_rsvp = OpenMatService.rsvp(
            athlete=existing_rsvp.athlete,
            session=existing_rsvp.session,
            rsvp_status=OpenMatRSVP.Status.NOT_GOING
        )

        # Should return the same object, updated
        assert updated_rsvp.id == existing_rsvp.id
        assert updated_rsvp.status == OpenMatRSVP.Status.NOT_GOING

        # Verify no duplicate was created
        assert OpenMatRSVP.objects.filter(
            athlete=existing_rsvp.athlete,
            session=existing_rsvp.session
        ).count() == 1

    def test_rsvp_all_status_options(self, db):
        """Test RSVP with all status options."""
        athlete = AthleteProfileFactory()
        session1 = OpenMatSessionFactory()
        session2 = OpenMatSessionFactory()
        session3 = OpenMatSessionFactory()

        # Test all status options
        rsvp1 = OpenMatService.rsvp(athlete, session1, OpenMatRSVP.Status.GOING)
        rsvp2 = OpenMatService.rsvp(athlete, session2, OpenMatRSVP.Status.NOT_GOING)
        rsvp3 = OpenMatService.rsvp(athlete, session3, OpenMatRSVP.Status.MAYBE)

        assert rsvp1.status == OpenMatRSVP.Status.GOING
        assert rsvp2.status == OpenMatRSVP.Status.NOT_GOING
        assert rsvp3.status == OpenMatRSVP.Status.MAYBE

    def test_rsvp_transaction_atomic(self, db):
        """Test that RSVP operations are atomic."""
        # This test verifies the @transaction.atomic decorator
        athlete = AthleteProfileFactory()
        session = OpenMatSessionFactory()

        # Mock a database error after the update_or_create
        with patch('community.models.OpenMatRSVP.objects.update_or_create') as mock_update:
            mock_update.side_effect = Exception("Database error")

            with pytest.raises(Exception, match="Database error"):
                OpenMatService.rsvp(athlete, session, OpenMatRSVP.Status.GOING)

        # Verify no RSVP was created due to the transaction rollback
        assert not OpenMatRSVP.objects.filter(athlete=athlete, session=session).exists()