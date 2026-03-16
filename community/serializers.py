from rest_framework import serializers

from .models import Achievement, AthleteAchievement, OpenMatRSVP, OpenMatSession


class AchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Achievement
        fields = ["id", "name", "description", "icon_url", "trigger_type", "trigger_value"]


class AthleteAchievementSerializer(serializers.ModelSerializer):
    achievement = AchievementSerializer(read_only=True)

    class Meta:
        model = AthleteAchievement
        fields = ["id", "athlete", "achievement", "awarded_by", "created_at"]
        read_only_fields = ["created_at"]


class OpenMatSessionSerializer(serializers.ModelSerializer):
    going_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = OpenMatSession
        fields = [
            "id", "academy", "title", "event_date", "start_time", "end_time",
            "max_capacity", "description", "is_cancelled", "going_count",
        ]


class OpenMatRSVPSerializer(serializers.ModelSerializer):
    athlete_name = serializers.CharField(source="athlete.user.username", read_only=True)

    class Meta:
        model = OpenMatRSVP
        fields = ["id", "session", "athlete", "athlete_name", "status", "created_at"]
        read_only_fields = ["created_at"]


class AthleteStatsSerializer(serializers.Serializer):
    total_check_ins = serializers.IntegerField()
    mat_hours = serializers.FloatField()
    current_streak_days = serializers.IntegerField()
    achievements_count = serializers.IntegerField()
