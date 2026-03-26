from rest_framework import serializers

from .models import (Achievement, AthleteAchievement, OpenMatRSVP,
                     OpenMatSession)


class AchievementSerializer(serializers.ModelSerializer):
    """Serializes a platform-wide achievement definition (badge)."""

    class Meta:
        model = Achievement
        fields = [
            "id",
            "name",
            "description",
            "icon_url",
            "trigger_type",
            "trigger_value",
        ]


class AthleteAchievementSerializer(serializers.ModelSerializer):
    """
    Serializes a record of an athlete having earned an achievement.

    Nests the full AchievementSerializer for read convenience. awarded_by is
    populated for manually-awarded badges and null for auto-triggered ones.
    """

    achievement = AchievementSerializer(read_only=True)

    class Meta:
        model = AthleteAchievement
        fields = ["id", "athlete", "achievement", "awarded_by", "created_at"]
        read_only_fields = ["created_at"]


class OpenMatSessionSerializer(serializers.ModelSerializer):
    """
    Serializes an open mat session for list and detail responses.

    going_count is populated by the DB-level annotation (annotated_going_count) added in
    community.selectors.get_upcoming_open_mats() — it is an annotated
    integer, not a property call, so the list endpoint issues only one query
    regardless of how many sessions are returned (P1 N+1 fix).
    """

    going_count = serializers.IntegerField(source='annotated_going_count', read_only=True)

    class Meta:
        model = OpenMatSession
        fields = [
            "id",
            "academy",
            "title",
            "event_date",
            "start_time",
            "end_time",
            "max_capacity",
            "description",
            "is_cancelled",
            "going_count",
        ]


class OpenMatRSVPSerializer(serializers.ModelSerializer):
    """Serializes an athlete RSVP for an open mat session (GOING / NOT_GOING / MAYBE)."""

    athlete_name = serializers.CharField(source="athlete.user.username", read_only=True)

    class Meta:
        model = OpenMatRSVP
        fields = ["id", "session", "athlete", "athlete_name", "status", "created_at"]
        read_only_fields = ["created_at"]


class AthleteStatsSerializer(serializers.Serializer):
    """
    Read-only serializer for the stats dict returned by
    StatsAggregationService.get_summary(athlete).
    """

    total_check_ins = serializers.IntegerField()
    mat_hours = serializers.FloatField()
    current_streak_days = serializers.IntegerField()
    achievements_count = serializers.IntegerField()
