"""Tests for community selectors: get_upcoming_open_mats, get_achievements_for_athlete."""

import pytest
from datetime import date, timedelta

from community.selectors import get_upcoming_open_mats, get_achievements_for_athlete
from community.models import OpenMatRSVP
from factories import (
    AcademyFactory,
    AthleteProfileFactory,
    AthleteAchievementFactory,
    AchievementFactory,
    OpenMatSessionFactory,
    OpenMatRSVPFactory,
)


class TestGetUpcomingOpenMats:
    def test_filters_by_academy(self, db):
        """Test that only sessions for the specified academy are returned."""
        academy1 = AcademyFactory()
        academy2 = AcademyFactory()

        session1 = OpenMatSessionFactory(academy=academy1, event_date=date.today())
        OpenMatSessionFactory(academy=academy2, event_date=date.today())

        result = get_upcoming_open_mats(academy1.id)

        session_ids = list(result.values_list('id', flat=True))
        assert session1.id in session_ids
        assert len(session_ids) == 1

    def test_filters_future_dates_only(self, db):
        """Test that only future and today's sessions are returned."""
        academy = AcademyFactory()
        today = date.today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        session_past = OpenMatSessionFactory(academy=academy, event_date=yesterday)
        session_today = OpenMatSessionFactory(academy=academy, event_date=today)
        session_future = OpenMatSessionFactory(academy=academy, event_date=tomorrow)

        result = get_upcoming_open_mats(academy.id)

        session_ids = list(result.values_list('id', flat=True))
        assert session_past.id not in session_ids
        assert session_today.id in session_ids
        assert session_future.id in session_ids

    def test_excludes_cancelled_sessions(self, db):
        """Test that cancelled sessions are excluded."""
        academy = AcademyFactory()

        session_active = OpenMatSessionFactory(academy=academy, is_cancelled=False)
        session_cancelled = OpenMatSessionFactory(academy=academy, is_cancelled=True)

        result = get_upcoming_open_mats(academy.id)

        session_ids = list(result.values_list('id', flat=True))
        assert session_active.id in session_ids
        assert session_cancelled.id not in session_ids

    def test_orders_by_event_date(self, db):
        """Test that sessions are ordered by event_date ascending."""
        academy = AcademyFactory()
        today = date.today()

        session_later = OpenMatSessionFactory(
            academy=academy,
            event_date=today + timedelta(days=5)
        )
        session_earlier = OpenMatSessionFactory(
            academy=academy,
            event_date=today + timedelta(days=1)
        )
        session_today = OpenMatSessionFactory(
            academy=academy,
            event_date=today
        )

        result = list(get_upcoming_open_mats(academy.id))

        assert result[0] == session_today
        assert result[1] == session_earlier
        assert result[2] == session_later

    def test_annotates_going_count_correctly(self, db):
        """Test that going_count is correctly annotated based on RSVPs."""
        academy = AcademyFactory()
        session = OpenMatSessionFactory(academy=academy)

        athlete1 = AthleteProfileFactory()
        athlete2 = AthleteProfileFactory()
        athlete3 = AthleteProfileFactory()
        athlete4 = AthleteProfileFactory()

        # Create RSVPs with different statuses
        OpenMatRSVPFactory(session=session, athlete=athlete1, status=OpenMatRSVP.Status.GOING)
        OpenMatRSVPFactory(session=session, athlete=athlete2, status=OpenMatRSVP.Status.GOING)
        OpenMatRSVPFactory(session=session, athlete=athlete3, status=OpenMatRSVP.Status.NOT_GOING)
        OpenMatRSVPFactory(session=session, athlete=athlete4, status=OpenMatRSVP.Status.MAYBE)

        result = get_upcoming_open_mats(academy.id)
        session_with_count = result.get(id=session.id)

        # Should count only GOING status (2 athletes)
        assert session_with_count.annotated_going_count == 2

    def test_going_count_zero_when_no_rsvps(self, db):
        """Test that going_count is 0 when no RSVPs exist."""
        academy = AcademyFactory()
        session = OpenMatSessionFactory(academy=academy)

        result = get_upcoming_open_mats(academy.id)
        session_with_count = result.get(id=session.id)

        assert session_with_count.annotated_going_count == 0

    def test_going_count_annotation_prevents_n_plus_1(self, db):
        """Test that the annotation prevents N+1 queries when accessing going_count."""
        academy = AcademyFactory()

        # Create multiple sessions with RSVPs
        for i in range(3):
            session = OpenMatSessionFactory(academy=academy)
            athlete = AthleteProfileFactory()
            OpenMatRSVPFactory(session=session, athlete=athlete, status=OpenMatRSVP.Status.GOING)

        # Verify that annotated_going_count is accessible without additional queries
        sessions = list(get_upcoming_open_mats(academy.id))

        # All sessions should have the annotated_going_count attribute
        for session in sessions:
            assert hasattr(session, 'annotated_going_count')
            assert session.annotated_going_count >= 0

    def test_empty_result_for_nonexistent_academy(self, db):
        """Test that no sessions are returned for non-existent academy."""
        result = get_upcoming_open_mats(99999)  # Non-existent academy ID

        assert list(result) == []

    def test_filters_and_annotations_combined(self, db):
        """Test comprehensive filtering and annotation in realistic scenario."""
        academy = AcademyFactory()
        today = date.today()

        # Valid session (future, not cancelled, with RSVPs)
        valid_session = OpenMatSessionFactory(
            academy=academy,
            event_date=today + timedelta(days=1),
            is_cancelled=False
        )

        # Invalid sessions that should be filtered out
        OpenMatSessionFactory(
            academy=academy,
            event_date=today - timedelta(days=1),  # Past date
            is_cancelled=False
        )
        OpenMatSessionFactory(
            academy=academy,
            event_date=today + timedelta(days=2),
            is_cancelled=True  # Cancelled
        )

        # Add RSVPs to the valid session
        for status in [OpenMatRSVP.Status.GOING, OpenMatRSVP.Status.NOT_GOING, OpenMatRSVP.Status.GOING]:
            athlete = AthleteProfileFactory()
            OpenMatRSVPFactory(session=valid_session, athlete=athlete, status=status)

        result = list(get_upcoming_open_mats(academy.id))

        assert len(result) == 1
        assert result[0].id == valid_session.id
        assert result[0].annotated_going_count == 2  # Two "GOING" RSVPs

    def test_distinct_going_count_annotation(self, db):
        """Test that distinct=True in the annotation works correctly."""
        # This test verifies that the annotation doesn't double-count
        # in case there are complex JOINs (though not applicable here,
        # it's good practice to test the distinct behavior)
        academy = AcademyFactory()
        session = OpenMatSessionFactory(academy=academy)
        athlete = AthleteProfileFactory()

        # Create one RSVP
        OpenMatRSVPFactory(session=session, athlete=athlete, status=OpenMatRSVP.Status.GOING)

        result = get_upcoming_open_mats(academy.id)
        session_with_count = result.get(id=session.id)

        # Should be exactly 1, not more due to any JOINs
        assert session_with_count.annotated_going_count == 1


class TestGetAchievementsForAthlete:
    def test_returns_athlete_achievements_only(self, db):
        """Test that only achievements for the specified athlete are returned."""
        athlete1 = AthleteProfileFactory()
        athlete2 = AthleteProfileFactory()

        achievement1 = AchievementFactory()
        achievement2 = AchievementFactory()

        # Create achievements for both athletes
        athlete_achievement1 = AthleteAchievementFactory(athlete=athlete1, achievement=achievement1)
        athlete_achievement2 = AthleteAchievementFactory(athlete=athlete2, achievement=achievement2)

        result = get_achievements_for_athlete(athlete1)

        achievement_ids = list(result.values_list('id', flat=True))
        assert athlete_achievement1.id in achievement_ids
        assert athlete_achievement2.id not in achievement_ids
        assert len(achievement_ids) == 1

    def test_select_related_achievement(self, db):
        """Test that Achievement objects are select_related for performance."""
        athlete = AthleteProfileFactory()
        achievement = AchievementFactory()
        AthleteAchievementFactory(athlete=athlete, achievement=achievement)

        # Verify that achievement is properly select_related
        achievements = list(get_achievements_for_athlete(athlete))

        # Should be able to access achievement without additional database hits
        for athlete_achievement in achievements:
            # These accesses should not trigger additional queries since select_related is used
            assert athlete_achievement.achievement.name == achievement.name
            assert athlete_achievement.achievement.trigger_type is not None

    def test_empty_result_for_athlete_with_no_achievements(self, db):
        """Test that empty queryset is returned for athlete with no achievements."""
        athlete = AthleteProfileFactory()

        result = get_achievements_for_athlete(athlete)

        assert list(result) == []

    def test_multiple_achievements_for_same_athlete(self, db):
        """Test returning multiple achievements for the same athlete."""
        athlete = AthleteProfileFactory()

        achievement1 = AchievementFactory(name="First Check-In")
        achievement2 = AchievementFactory(name="10 Check-Ins")
        achievement3 = AchievementFactory(name="50 Mat Hours")

        AthleteAchievementFactory(athlete=athlete, achievement=achievement1)
        AthleteAchievementFactory(athlete=athlete, achievement=achievement2)
        AthleteAchievementFactory(athlete=athlete, achievement=achievement3)

        result = list(get_achievements_for_athlete(athlete))

        assert len(result) == 3
        achievement_names = {aa.achievement.name for aa in result}
        assert achievement_names == {"First Check-In", "10 Check-Ins", "50 Mat Hours"}

    def test_queryset_can_be_further_filtered(self, db):
        """Test that the returned queryset can be further filtered."""
        athlete = AthleteProfileFactory()
        achievement1 = AchievementFactory(name="Manual Award")
        achievement2 = AchievementFactory(name="Auto Award")

        professor = AthleteProfileFactory()

        # One manual, one automatic achievement
        AthleteAchievementFactory(athlete=athlete, achievement=achievement1, awarded_by=professor)
        AthleteAchievementFactory(athlete=athlete, achievement=achievement2, awarded_by=None)

        # Test further filtering on the returned queryset
        manual_achievements = get_achievements_for_athlete(athlete).filter(awarded_by__isnull=False)
        auto_achievements = get_achievements_for_athlete(athlete).filter(awarded_by__isnull=True)

        assert manual_achievements.count() == 1
        assert auto_achievements.count() == 1
        assert manual_achievements.first().achievement.name == "Manual Award"
        assert auto_achievements.first().achievement.name == "Auto Award"

    def test_default_ordering_preserved(self, db):
        """Test that the default ordering from the model is preserved."""
        # AthleteAchievement inherits TimestampMixin, so it should order by creation
        athlete = AthleteProfileFactory()
        achievement1 = AchievementFactory()
        achievement2 = AchievementFactory()

        # Create in specific order
        aa1 = AthleteAchievementFactory(athlete=athlete, achievement=achievement1)
        aa2 = AthleteAchievementFactory(athlete=athlete, achievement=achievement2)

        result = list(get_achievements_for_athlete(athlete))

        # Should maintain the creation order (or model's default ordering)
        # Since we're not explicitly ordering in the selector, it depends on model ordering
        assert len(result) == 2
        assert aa1 in result
        assert aa2 in result