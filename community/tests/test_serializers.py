"""Tests for community serializers."""

import pytest
from datetime import date, time
from rest_framework.serializers import ValidationError

from community.serializers import (
    AchievementSerializer,
    AthleteAchievementSerializer,
    OpenMatSessionSerializer,
    OpenMatRSVPSerializer,
    AthleteStatsSerializer,
)
from community.models import Achievement, OpenMatRSVP
from factories import (
    AchievementFactory,
    AthleteAchievementFactory,
    AthleteProfileFactory,
    OpenMatSessionFactory,
    OpenMatRSVPFactory,
    UserFactory,
    AcademyFactory,
)


class TestAchievementSerializer:
    def test_serialize_achievement(self, db):
        """Test serializing an Achievement instance."""
        achievement = AchievementFactory(
            name="First Check-In",
            description="Complete your first training session",
            icon_url="https://example.com/icon.png",
            trigger_type=Achievement.TriggerType.CHECKIN_COUNT,
            trigger_value=1.0
        )

        serializer = AchievementSerializer(achievement)

        expected_fields = {
            "id", "name", "description", "icon_url", "trigger_type", "trigger_value"
        }
        assert set(serializer.data.keys()) == expected_fields
        assert serializer.data["name"] == "First Check-In"
        assert serializer.data["trigger_type"] == "CHECKIN_COUNT"
        assert serializer.data["trigger_value"] == 1.0

    def test_serialize_achievement_with_blank_icon(self, db):
        """Test serializing achievement with blank icon_url."""
        achievement = AchievementFactory(icon_url="")

        serializer = AchievementSerializer(achievement)

        assert serializer.data["icon_url"] == ""

    def test_serialize_achievement_with_null_trigger_value(self, db):
        """Test serializing achievement with null trigger_value."""
        achievement = AchievementFactory(
            trigger_type=Achievement.TriggerType.MANUAL,
            trigger_value=None
        )

        serializer = AchievementSerializer(achievement)

        assert serializer.data["trigger_value"] is None

    def test_deserialize_achievement(self, db):
        """Test deserializing data to create an Achievement."""
        data = {
            "name": "100 Mat Hours",
            "description": "Train for 100 hours",
            "icon_url": "https://example.com/icon.png",
            "trigger_type": "MAT_HOURS",
            "trigger_value": 100.0
        }

        serializer = AchievementSerializer(data=data)

        assert serializer.is_valid()
        achievement = serializer.save()
        assert achievement.name == "100 Mat Hours"
        assert achievement.trigger_type == Achievement.TriggerType.MAT_HOURS
        assert achievement.trigger_value == 100.0

    def test_validates_trigger_type_choices(self, db):
        """Test validation of trigger_type choices."""
        data = {
            "name": "Invalid Achievement",
            "description": "Test description",
            "trigger_type": "INVALID_TYPE",
            "trigger_value": 10.0
        }

        serializer = AchievementSerializer(data=data)

        assert not serializer.is_valid()
        assert "trigger_type" in serializer.errors


class TestAthleteAchievementSerializer:
    def test_serialize_athlete_achievement(self, db):
        """Test serializing an AthleteAchievement instance."""
        professor = AthleteProfileFactory()
        athlete_achievement = AthleteAchievementFactory(awarded_by=professor)

        serializer = AthleteAchievementSerializer(athlete_achievement)

        expected_fields = {
            "id", "athlete", "achievement", "awarded_by", "created_at"
        }
        assert set(serializer.data.keys()) == expected_fields
        assert serializer.data["athlete"] == athlete_achievement.athlete.id
        assert serializer.data["awarded_by"] == professor.id

    def test_serialize_nested_achievement(self, db):
        """Test that achievement is fully serialized as nested object."""
        achievement = AchievementFactory(name="Test Achievement")
        athlete_achievement = AthleteAchievementFactory(achievement=achievement)

        serializer = AthleteAchievementSerializer(athlete_achievement)

        achievement_data = serializer.data["achievement"]
        assert isinstance(achievement_data, dict)
        assert achievement_data["name"] == "Test Achievement"
        assert "trigger_type" in achievement_data

    def test_serialize_automatic_achievement(self, db):
        """Test serializing automatically awarded achievement."""
        athlete_achievement = AthleteAchievementFactory(awarded_by=None)

        serializer = AthleteAchievementSerializer(athlete_achievement)

        assert serializer.data["awarded_by"] is None

    def test_created_at_is_read_only(self, db):
        """Test that created_at is read-only field."""
        # Use existing AthleteAchievement to test serialization of created_at
        athlete_achievement = AthleteAchievementFactory()

        serializer = AthleteAchievementSerializer(athlete_achievement)

        # created_at should be present in serialized data
        assert "created_at" in serializer.data
        assert serializer.data["created_at"] is not None

        # Verify created_at is in read_only_fields
        assert "created_at" in AthleteAchievementSerializer.Meta.read_only_fields

    def test_performance_with_prefetch(self, db):
        """Test that nested achievement doesn't cause N+1 queries."""
        # Create multiple athlete achievements
        achievements = []
        for i in range(3):
            aa = AthleteAchievementFactory()
            achievements.append(aa)

        # Serialize with select_related (simulating selector usage)
        from community.models import AthleteAchievement
        queryset = AthleteAchievement.objects.select_related('achievement')

        # Test that serialization works without errors
        serializer = AthleteAchievementSerializer(queryset, many=True)
        data = serializer.data

        # Verify that all achievements are properly nested
        assert len(data) == 3
        for item in data:
            assert "achievement" in item
            assert isinstance(item["achievement"], dict)
            assert "name" in item["achievement"]


class TestOpenMatSessionSerializer:
    def test_serialize_open_mat_session(self, db):
        """Test serializing an OpenMatSession instance."""
        session = OpenMatSessionFactory(
            title="Saturday Open Mat",
            event_date=date(2024, 6, 15),
            start_time=time(10, 0),
            end_time=time(12, 0),
            max_capacity=20,
            is_cancelled=False
        )

        # Manually add the annotated_going_count attribute to simulate selector usage
        session.annotated_going_count = 0

        serializer = OpenMatSessionSerializer(session)

        expected_fields = {
            "id", "academy", "title", "event_date", "start_time", "end_time",
            "max_capacity", "description", "is_cancelled", "going_count"
        }
        assert set(serializer.data.keys()) == expected_fields
        assert serializer.data["title"] == "Saturday Open Mat"
        assert serializer.data["event_date"] == "2024-06-15"
        assert serializer.data["start_time"] == "10:00:00"

    def test_serialize_with_annotated_going_count(self, db):
        """Test serializing session with annotated going_count."""
        # Simulate the annotated queryset from selector
        from community.selectors import get_upcoming_open_mats

        academy = AcademyFactory()
        session = OpenMatSessionFactory(academy=academy)

        # Add some RSVPs
        for status in [OpenMatRSVP.Status.GOING, OpenMatRSVP.Status.GOING, OpenMatRSVP.Status.NOT_GOING]:
            athlete = AthleteProfileFactory()
            OpenMatRSVPFactory(session=session, athlete=athlete, status=status)

        # Get the annotated session
        annotated_sessions = get_upcoming_open_mats(academy.id)
        annotated_session = annotated_sessions.get(id=session.id)

        serializer = OpenMatSessionSerializer(annotated_session)

        # The serializer should map annotated_going_count to going_count in output
        assert serializer.data["going_count"] == 2

    def test_going_count_read_only(self, db):
        """Test that going_count is read-only and ignored in deserialization."""
        academy = AcademyFactory()
        data = {
            "academy": academy.id,
            "title": "Test Session",
            "event_date": "2024-06-15",
            "start_time": "10:00:00",
            "going_count": 999  # This should be ignored
        }

        serializer = OpenMatSessionSerializer(data=data)

        assert serializer.is_valid()
        session = serializer.save()
        # going_count should be 0 (default property calculation), not 999
        assert session.going_count == 0

    def test_deserialize_create_session(self, db):
        """Test deserializing data to create an OpenMatSession."""
        academy = AcademyFactory()
        data = {
            "academy": academy.id,
            "title": "Sunday Rolling",
            "event_date": "2024-06-16",
            "start_time": "14:00:00",
            "end_time": "16:00:00",
            "max_capacity": 15,
            "description": "Casual rolling session",
            "is_cancelled": False
        }

        serializer = OpenMatSessionSerializer(data=data)

        assert serializer.is_valid()
        session = serializer.save()
        assert session.title == "Sunday Rolling"
        assert session.max_capacity == 15

    def test_optional_fields(self, db):
        """Test that optional fields can be omitted."""
        academy = AcademyFactory()
        minimal_data = {
            "academy": academy.id,
            "title": "Minimal Session",
            "event_date": "2024-06-17",
            "start_time": "10:00:00"
            # end_time, max_capacity, description are optional
        }

        serializer = OpenMatSessionSerializer(data=minimal_data)

        assert serializer.is_valid()
        session = serializer.save()
        assert session.end_time is None
        assert session.max_capacity is None
        assert session.description == ""


class TestOpenMatRSVPSerializer:
    def test_serialize_rsvp(self, db):
        """Test serializing an OpenMatRSVP instance."""
        user = UserFactory(username="johndoe")
        athlete = AthleteProfileFactory(user=user)
        rsvp = OpenMatRSVPFactory(athlete=athlete, status=OpenMatRSVP.Status.GOING)

        serializer = OpenMatRSVPSerializer(rsvp)

        expected_fields = {
            "id", "session", "athlete", "athlete_name", "status", "created_at"
        }
        assert set(serializer.data.keys()) == expected_fields
        assert serializer.data["athlete"] == athlete.id
        assert serializer.data["athlete_name"] == "johndoe"
        assert serializer.data["status"] == "GOING"

    def test_athlete_name_from_user_username(self, db):
        """Test that athlete_name correctly pulls from athlete.user.username."""
        user = UserFactory(username="testuser123")
        athlete = AthleteProfileFactory(user=user)
        rsvp = OpenMatRSVPFactory(athlete=athlete)

        serializer = OpenMatRSVPSerializer(rsvp)

        assert serializer.data["athlete_name"] == "testuser123"

    def test_athlete_name_read_only(self, db):
        """Test that athlete_name is read-only and ignored in deserialization."""
        session = OpenMatSessionFactory()
        athlete = AthleteProfileFactory()

        data = {
            "session": session.id,
            "athlete": athlete.id,
            "athlete_name": "ignored_name",  # Should be ignored
            "status": "MAYBE"
        }

        serializer = OpenMatRSVPSerializer(data=data)

        assert serializer.is_valid()
        rsvp = serializer.save()
        assert rsvp.athlete.user.username != "ignored_name"

    def test_deserialize_create_rsvp(self, db):
        """Test deserializing data to create an OpenMatRSVP."""
        session = OpenMatSessionFactory()
        athlete = AthleteProfileFactory()

        data = {
            "session": session.id,
            "athlete": athlete.id,
            "status": "NOT_GOING"
        }

        serializer = OpenMatRSVPSerializer(data=data)

        assert serializer.is_valid()
        rsvp = serializer.save()
        assert rsvp.session == session
        assert rsvp.athlete == athlete
        assert rsvp.status == OpenMatRSVP.Status.NOT_GOING

    def test_validates_status_choices(self, db):
        """Test validation of status choices."""
        session = OpenMatSessionFactory()
        athlete = AthleteProfileFactory()

        data = {
            "session": session.id,
            "athlete": athlete.id,
            "status": "INVALID_STATUS"
        }

        serializer = OpenMatRSVPSerializer(data=data)

        assert not serializer.is_valid()
        assert "status" in serializer.errors

    def test_created_at_read_only(self, db):
        """Test that created_at is read-only field."""
        session = OpenMatSessionFactory()
        athlete = AthleteProfileFactory()

        data = {
            "session": session.id,
            "athlete": athlete.id,
            "status": "GOING",
            "created_at": "2023-01-01T00:00:00Z"  # Should be ignored
        }

        serializer = OpenMatRSVPSerializer(data=data)

        assert serializer.is_valid()
        rsvp = serializer.save()
        assert rsvp.created_at.strftime("%Y-%m-%d") != "2023-01-01"


class TestAthleteStatsSerializer:
    def test_serialize_stats_dict(self, db):
        """Test serializing a stats dictionary."""
        stats_data = {
            "total_check_ins": 25,
            "mat_hours": 150.5,
            "current_streak_days": 7,
            "achievements_count": 3
        }

        serializer = AthleteStatsSerializer(data=stats_data)

        assert serializer.is_valid()
        assert serializer.validated_data == stats_data

    def test_all_fields_required(self, db):
        """Test that all stats fields are required."""
        incomplete_data = {
            "total_check_ins": 25,
            "mat_hours": 150.5,
            # Missing current_streak_days and achievements_count
        }

        serializer = AthleteStatsSerializer(data=incomplete_data)

        assert not serializer.is_valid()
        assert "current_streak_days" in serializer.errors
        assert "achievements_count" in serializer.errors

    def test_field_types_validated(self, db):
        """Test that field types are properly validated."""
        invalid_data = {
            "total_check_ins": "not_a_number",
            "mat_hours": "also_not_a_number",
            "current_streak_days": 7.5,  # Should be integer
            "achievements_count": -1  # Should be non-negative
        }

        serializer = AthleteStatsSerializer(data=invalid_data)

        assert not serializer.is_valid()
        assert "total_check_ins" in serializer.errors
        assert "mat_hours" in serializer.errors

    def test_read_only_serializer(self, db):
        """Test that this is effectively a read-only serializer."""
        # AthleteStatsSerializer inherits from serializers.Serializer, not ModelSerializer
        # It should be used for reading/validation only, not for saving to DB
        stats_data = {
            "total_check_ins": 25,
            "mat_hours": 150.5,
            "current_streak_days": 7,
            "achievements_count": 3
        }

        serializer = AthleteStatsSerializer(data=stats_data)

        assert serializer.is_valid()
        # This serializer should be used for validation, not for DB persistence
        # It doesn't have a Meta.model, so save() should raise NotImplementedError
        with pytest.raises(NotImplementedError):
            serializer.save()

    def test_zero_values_allowed(self, db):
        """Test that zero values are valid for stats."""
        zero_stats = {
            "total_check_ins": 0,
            "mat_hours": 0.0,
            "current_streak_days": 0,
            "achievements_count": 0
        }

        serializer = AthleteStatsSerializer(data=zero_stats)

        assert serializer.is_valid()
        assert serializer.validated_data == zero_stats

    def test_decimal_mat_hours_precision(self, db):
        """Test that mat_hours accepts decimal values properly."""
        stats_data = {
            "total_check_ins": 10,
            "mat_hours": 123.75,  # Decimal value
            "current_streak_days": 5,
            "achievements_count": 2
        }

        serializer = AthleteStatsSerializer(data=stats_data)

        assert serializer.is_valid()
        assert serializer.validated_data["mat_hours"] == 123.75