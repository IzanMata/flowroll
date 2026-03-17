from django.contrib.auth import models as auth_models
from rest_framework import serializers

from .models import Match, MatchEvent


class UserMinimalSerializer(serializers.ModelSerializer):
    """Lightweight User representation used for athlete fields inside MatchSerializer."""

    class Meta:
        model = auth_models.User
        fields = ["id", "username"]


class MatchEventSerializer(serializers.ModelSerializer):
    """Serializes a single scoring event (points, advantage, penalty, submission) in a match."""

    athlete_name = serializers.ReadOnlyField(source="athlete.username")

    class Meta:
        model = MatchEvent
        fields = [
            "id",
            "athlete",
            "athlete_name",
            "timestamp",
            "points_awarded",
            "action_description",
            "event_type",
        ]


class MatchSerializer(serializers.ModelSerializer):
    """
    Full match representation including nested athlete details and event log.

    score_a, score_b, is_finished, winner, and date are read-only — they are
    managed by the add_event and finish_match actions, not by direct writes.
    """

    events = MatchEventSerializer(many=True, read_only=True)

    athlete_a_detail = UserMinimalSerializer(source="athlete_a", read_only=True)
    athlete_b_detail = UserMinimalSerializer(source="athlete_b", read_only=True)
    winner_detail = UserMinimalSerializer(source="winner", read_only=True)

    class Meta:
        model = Match
        fields = [
            "id",
            "athlete_a",
            "athlete_b",
            "athlete_a_detail",
            "athlete_b_detail",
            "date",
            "duration_seconds",
            "is_finished",
            "score_a",
            "score_b",
            "winner",
            "winner_detail",
            "events",
        ]

        read_only_fields = ["score_a", "score_b", "is_finished", "winner", "date"]
