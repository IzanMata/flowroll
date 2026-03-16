from rest_framework import serializers

from .models import Matchup, TimerPreset, TimerSession, WeightClass


class WeightClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeightClass
        fields = ["id", "name", "min_weight", "max_weight", "gender"]


class TimerPresetSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimerPreset
        fields = [
            "id", "academy", "name", "format", "round_duration_seconds",
            "rest_duration_seconds", "overtime_seconds", "rounds",
        ]


class TimerSessionSerializer(serializers.ModelSerializer):
    preset_name = serializers.CharField(source="preset.name", read_only=True)

    class Meta:
        model = TimerSession
        fields = [
            "id", "preset", "preset_name", "status", "current_round",
            "started_at", "paused_at", "elapsed_seconds",
        ]
        read_only_fields = ["started_at", "paused_at", "elapsed_seconds"]


class MatchupSerializer(serializers.ModelSerializer):
    athlete_a_name = serializers.CharField(source="athlete_a.user.username", read_only=True)
    athlete_b_name = serializers.CharField(source="athlete_b.user.username", read_only=True)
    winner_name = serializers.CharField(source="winner.user.username", read_only=True, allow_null=True)

    class Meta:
        model = Matchup
        fields = [
            "id", "academy", "athlete_a", "athlete_a_name",
            "athlete_b", "athlete_b_name", "weight_class",
            "match_format", "round_number", "status",
            "winner", "winner_name", "created_at",
        ]
        read_only_fields = ["created_at"]


class PairAthletesSerializer(serializers.Serializer):
    """Input for the pair_athletes action."""
    athlete_ids = serializers.ListField(child=serializers.IntegerField(), min_length=2)
    match_format = serializers.ChoiceField(choices=Matchup.MatchFormat.choices)
    weight_class_id = serializers.IntegerField(required=False, allow_null=True)
    academy_id = serializers.IntegerField()
