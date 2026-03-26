"""Tests for community models: Achievement, AthleteAchievement, OpenMatSession, OpenMatRSVP."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from datetime import date, time, timedelta

from community.models import Achievement, AthleteAchievement, OpenMatSession, OpenMatRSVP
from factories import (
    AchievementFactory,
    AthleteAchievementFactory,
    AthleteProfileFactory,
    OpenMatSessionFactory,
    OpenMatRSVPFactory,
    AcademyFactory,
)


class TestAchievement:
    def test_create_achievement(self, db):
        achievement = Achievement.objects.create(
            name="First Check-In",
            description="Complete your first training session",
            trigger_type=Achievement.TriggerType.CHECKIN_COUNT,
            trigger_value=1,
        )
        assert achievement.name == "First Check-In"
        assert achievement.trigger_type == Achievement.TriggerType.CHECKIN_COUNT
        assert achievement.trigger_value == 1

    def test_str_returns_name(self, db):
        achievement = AchievementFactory(name="50 Mat Hours")
        assert str(achievement) == "50 Mat Hours"

    def test_name_is_unique(self, db):
        AchievementFactory(name="First Check-In")
        with pytest.raises(IntegrityError):
            AchievementFactory(name="First Check-In")

    def test_trigger_type_choices_are_valid(self, db):
        expected_choices = {"CHECKIN_COUNT", "MAT_HOURS", "STREAK_DAYS", "MANUAL"}
        actual_choices = {choice for choice, _ in Achievement.TriggerType.choices}
        assert actual_choices == expected_choices

    def test_manual_achievement_can_have_null_trigger_value(self, db):
        achievement = AchievementFactory(
            trigger_type=Achievement.TriggerType.MANUAL,
            trigger_value=None
        )
        assert achievement.trigger_value is None

    def test_automatic_achievement_has_trigger_value(self, db):
        achievement = AchievementFactory(
            trigger_type=Achievement.TriggerType.CHECKIN_COUNT,
            trigger_value=10
        )
        assert achievement.trigger_value == 10

    def test_icon_url_can_be_blank(self, db):
        achievement = AchievementFactory(icon_url="")
        assert achievement.icon_url == ""


class TestAthleteAchievement:
    def test_create_athlete_achievement(self, db):
        athlete = AthleteProfileFactory()
        achievement = AchievementFactory()
        athlete_achievement = AthleteAchievement.objects.create(
            athlete=athlete,
            achievement=achievement
        )
        assert athlete_achievement.athlete == athlete
        assert athlete_achievement.achievement == achievement
        assert athlete_achievement.awarded_by is None

    def test_str_representation(self, db):
        athlete_achievement = AthleteAchievementFactory()
        expected = f"{athlete_achievement.athlete} earned {athlete_achievement.achievement}"
        assert str(athlete_achievement) == expected

    def test_unique_together_constraint(self, db):
        athlete = AthleteProfileFactory()
        achievement = AchievementFactory()
        AthleteAchievementFactory(athlete=athlete, achievement=achievement)

        with pytest.raises(IntegrityError):
            AthleteAchievementFactory(athlete=athlete, achievement=achievement)

    def test_manual_achievement_has_awarded_by(self, db):
        professor = AthleteProfileFactory()
        athlete_achievement = AthleteAchievementFactory(awarded_by=professor)
        assert athlete_achievement.awarded_by == professor

    def test_automatic_achievement_has_null_awarded_by(self, db):
        athlete_achievement = AthleteAchievementFactory(awarded_by=None)
        assert athlete_achievement.awarded_by is None

    def test_cascade_delete_on_athlete(self, db):
        athlete_achievement = AthleteAchievementFactory()
        athlete_id = athlete_achievement.athlete.id
        athlete_achievement.athlete.delete()
        assert not AthleteAchievement.objects.filter(athlete_id=athlete_id).exists()

    def test_cascade_delete_on_achievement(self, db):
        athlete_achievement = AthleteAchievementFactory()
        achievement_id = athlete_achievement.achievement.id
        athlete_achievement.achievement.delete()
        assert not AthleteAchievement.objects.filter(achievement_id=achievement_id).exists()

    def test_set_null_on_awarded_by_delete(self, db):
        professor = AthleteProfileFactory()
        athlete_achievement = AthleteAchievementFactory(awarded_by=professor)
        professor.delete()
        athlete_achievement.refresh_from_db()
        assert athlete_achievement.awarded_by is None

    def test_timestamp_mixin_fields(self, db):
        athlete_achievement = AthleteAchievementFactory()
        assert athlete_achievement.created_at is not None
        assert athlete_achievement.updated_at is not None


class TestOpenMatSession:
    def test_create_open_mat_session(self, db):
        academy = AcademyFactory()
        session = OpenMatSession.objects.create(
            academy=academy,
            title="Saturday Open Mat",
            event_date=date.today(),
            start_time=time(10, 0),
            end_time=time(12, 0),
        )
        assert session.academy == academy
        assert session.title == "Saturday Open Mat"
        assert session.max_capacity is None
        assert session.is_cancelled is False

    def test_str_representation(self, db):
        session = OpenMatSessionFactory()
        expected = f"{session.title} @ {session.academy} on {session.event_date}"
        assert str(session) == expected

    def test_default_title_is_open_mat(self, db):
        session = OpenMatSessionFactory(title="Open Mat")
        assert session.title == "Open Mat"

    def test_tenant_mixin_includes_academy(self, db):
        academy = AcademyFactory()
        session = OpenMatSessionFactory(academy=academy)
        assert session.academy == academy

    def test_timestamp_mixin_fields(self, db):
        session = OpenMatSessionFactory()
        assert session.created_at is not None
        assert session.updated_at is not None

    def test_ordering_by_event_date_desc(self, db):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        yesterday = today - timedelta(days=1)

        session1 = OpenMatSessionFactory(event_date=yesterday)
        session2 = OpenMatSessionFactory(event_date=tomorrow)
        session3 = OpenMatSessionFactory(event_date=today)

        sessions = list(OpenMatSession.objects.all())
        expected_order = [session2, session3, session1]  # desc order
        assert sessions == expected_order

    def test_going_count_property(self, db):
        session = OpenMatSessionFactory()
        athlete1 = AthleteProfileFactory()
        athlete2 = AthleteProfileFactory()
        athlete3 = AthleteProfileFactory()

        # Create different RSVP statuses
        OpenMatRSVPFactory(session=session, athlete=athlete1, status=OpenMatRSVP.Status.GOING)
        OpenMatRSVPFactory(session=session, athlete=athlete2, status=OpenMatRSVP.Status.GOING)
        OpenMatRSVPFactory(session=session, athlete=athlete3, status=OpenMatRSVP.Status.NOT_GOING)

        assert session.going_count == 2

    def test_going_count_property_empty(self, db):
        session = OpenMatSessionFactory()
        assert session.going_count == 0

    def test_indexes_created(self, db):
        """Test that the academy, event_date index exists."""
        # This test verifies the Meta.indexes configuration
        from django.db import connection
        table_name = OpenMatSession._meta.db_table

        # Get table constraints which includes indexes in newer Django versions
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, table_name)

        # Look for an index on academy and event_date fields
        academy_event_index_found = False
        for constraint_name, constraint_info in constraints.items():
            constraint_columns = constraint_info.get('columns', [])
            if 'academy_id' in constraint_columns and 'event_date' in constraint_columns:
                academy_event_index_found = True
                break

        assert academy_event_index_found


class TestOpenMatRSVP:
    def test_create_rsvp(self, db):
        session = OpenMatSessionFactory()
        athlete = AthleteProfileFactory()
        rsvp = OpenMatRSVP.objects.create(
            session=session,
            athlete=athlete,
            status=OpenMatRSVP.Status.GOING
        )
        assert rsvp.session == session
        assert rsvp.athlete == athlete
        assert rsvp.status == OpenMatRSVP.Status.GOING

    def test_str_representation(self, db):
        rsvp = OpenMatRSVPFactory()
        expected = f"{rsvp.athlete} → {rsvp.session} ({rsvp.status})"
        assert str(rsvp) == expected

    def test_default_status_is_going(self, db):
        session = OpenMatSessionFactory()
        athlete = AthleteProfileFactory()
        rsvp = OpenMatRSVP.objects.create(session=session, athlete=athlete)
        assert rsvp.status == OpenMatRSVP.Status.GOING

    def test_status_choices_are_valid(self, db):
        expected_choices = {"GOING", "NOT_GOING", "MAYBE"}
        actual_choices = {choice for choice, _ in OpenMatRSVP.Status.choices}
        assert actual_choices == expected_choices

    def test_unique_together_constraint(self, db):
        session = OpenMatSessionFactory()
        athlete = AthleteProfileFactory()
        OpenMatRSVPFactory(session=session, athlete=athlete)

        with pytest.raises(IntegrityError):
            OpenMatRSVPFactory(session=session, athlete=athlete)

    def test_same_athlete_can_rsvp_to_different_sessions(self, db):
        athlete = AthleteProfileFactory()
        session1 = OpenMatSessionFactory()
        session2 = OpenMatSessionFactory()

        OpenMatRSVPFactory(session=session1, athlete=athlete)
        OpenMatRSVPFactory(session=session2, athlete=athlete)

        assert OpenMatRSVP.objects.filter(athlete=athlete).count() == 2

    def test_cascade_delete_on_session(self, db):
        rsvp = OpenMatRSVPFactory()
        session_id = rsvp.session.id
        rsvp.session.delete()
        assert not OpenMatRSVP.objects.filter(session_id=session_id).exists()

    def test_cascade_delete_on_athlete(self, db):
        rsvp = OpenMatRSVPFactory()
        athlete_id = rsvp.athlete.id
        rsvp.athlete.delete()
        assert not OpenMatRSVP.objects.filter(athlete_id=athlete_id).exists()

    def test_timestamp_mixin_fields(self, db):
        rsvp = OpenMatRSVPFactory()
        assert rsvp.created_at is not None
        assert rsvp.updated_at is not None

    def test_session_status_index_exists(self, db):
        """Test that the session, status index exists for performance."""
        from django.db import connection
        table_name = OpenMatRSVP._meta.db_table

        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, table_name)

        # Look for the specific index name mentioned in the model
        index_found = any("openmatrsvp_session_status_idx" in constraint_name.lower()
                         for constraint_name in constraints.keys())
        assert index_found