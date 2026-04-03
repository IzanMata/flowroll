from rest_framework import serializers

from .models import AthleteMatchStats


class AthleteMatchStatsSerializer(serializers.ModelSerializer):
    athlete_username = serializers.ReadOnlyField(source="athlete.user.username")
    win_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = AthleteMatchStats
        fields = [
            "id",
            "athlete",
            "athlete_username",
            "total_matches",
            "wins",
            "losses",
            "draws",
            "win_rate",
            "total_points_scored",
            "total_points_conceded",
            "submissions_won",
            "updated_at",
        ]
        read_only_fields = [
            "total_matches",
            "wins",
            "losses",
            "draws",
            "win_rate",
            "total_points_scored",
            "total_points_conceded",
            "submissions_won",
            "updated_at",
        ]
