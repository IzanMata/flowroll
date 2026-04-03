from rest_framework import serializers

from athletes.serializers import AthleteProfileSerializer

from .models import (Tournament, TournamentDivision, TournamentMatch,
                     TournamentParticipant)


class TournamentDivisionSerializer(serializers.ModelSerializer):
    confirmed_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = TournamentDivision
        fields = [
            "id",
            "name",
            "belt_min",
            "belt_max",
            "weight_min",
            "weight_max",
            "confirmed_count",
        ]


class TournamentSerializer(serializers.ModelSerializer):
    divisions = TournamentDivisionSerializer(many=True, read_only=True)
    participant_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Tournament
        fields = [
            "id",
            "name",
            "description",
            "date",
            "location",
            "status",
            "format",
            "max_participants",
            "participant_count",
            "divisions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "created_at", "updated_at"]


class TournamentParticipantSerializer(serializers.ModelSerializer):
    athlete_username = serializers.ReadOnlyField(source="athlete.user.username")
    division_name = serializers.ReadOnlyField(source="division.name")

    class Meta:
        model = TournamentParticipant
        fields = [
            "id",
            "athlete",
            "athlete_username",
            "division",
            "division_name",
            "status",
            "belt_at_registration",
            "weight_at_registration",
            "seed",
        ]
        read_only_fields = [
            "status",
            "belt_at_registration",
            "weight_at_registration",
            "seed",
        ]


class TournamentMatchSerializer(serializers.ModelSerializer):
    athlete_a_username = serializers.ReadOnlyField(source="athlete_a.user.username")
    athlete_b_username = serializers.ReadOnlyField(source="athlete_b.user.username")
    winner_username = serializers.ReadOnlyField(source="winner.user.username")
    division_name = serializers.ReadOnlyField(source="division.name")

    class Meta:
        model = TournamentMatch
        fields = [
            "id",
            "tournament",
            "division",
            "division_name",
            "round_number",
            "athlete_a",
            "athlete_a_username",
            "athlete_b",
            "athlete_b_username",
            "winner",
            "winner_username",
            "score_a",
            "score_b",
            "is_finished",
            "notes",
        ]
        read_only_fields = [
            "round_number",
            "winner",
            "score_a",
            "score_b",
            "is_finished",
        ]


class RecordMatchResultSerializer(serializers.Serializer):
    winner_id = serializers.IntegerField()
    score_a = serializers.IntegerField(default=0, min_value=0)
    score_b = serializers.IntegerField(default=0, min_value=0)
    notes = serializers.CharField(max_length=300, allow_blank=True, default="")


class RegisterParticipantSerializer(serializers.Serializer):
    athlete_id = serializers.IntegerField()
    division_id = serializers.IntegerField(required=False, allow_null=True)
