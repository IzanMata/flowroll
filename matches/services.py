"""
Business logic for match management and scoring.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import F

from .models import Match, MatchEvent


class MatchService:
    """Handles match creation, scoring events, and match finalisation."""

    @staticmethod
    @transaction.atomic
    def add_event(
        match_pk: int,
        athlete_id: int,
        event_type: str,
        timestamp: int,
        action_description: str,
        points_awarded: int = 0,
    ) -> Match:
        """
        Record a scoring event in a match and update scores atomically.

        The match row is locked with select_for_update() so that concurrent
        calls cannot read stale score values. Score increments use F()
        expressions to avoid lost-update races.

        Raises ValueError if the athlete is not a participant.
        """
        match = Match.objects.select_for_update().get(pk=match_pk)

        if athlete_id not in (match.athlete_a_id, match.athlete_b_id):
            raise ValueError("Athlete is not a participant in this match.")

        if match.is_finished:
            raise ValueError("Cannot add events to a finished match.")

        MatchEvent.objects.create(
            match=match,
            athlete_id=athlete_id,
            timestamp=timestamp,
            points_awarded=points_awarded,
            action_description=action_description,
            event_type=event_type,
        )

        if event_type == MatchEvent.TypeChoices.POINTS and points_awarded > 0:
            if athlete_id == match.athlete_a_id:
                Match.objects.filter(pk=match.pk).update(score_a=F("score_a") + points_awarded)
            else:
                Match.objects.filter(pk=match.pk).update(score_b=F("score_b") + points_awarded)

        match.refresh_from_db()
        return match

    @staticmethod
    @transaction.atomic
    def finish_match(match_pk: int, winner_id: int) -> Match:
        """
        Mark a match as finished and declare the winner.

        Uses update() with specific fields so concurrent score changes from
        add_event() between get_object() and this call are not overwritten.

        Raises ValueError if winner_id is not one of the participants or
        the match is already finished.
        """
        match = Match.objects.select_for_update().get(pk=match_pk)

        if match.is_finished:
            raise ValueError("Match is already finished.")

        if winner_id not in (match.athlete_a_id, match.athlete_b_id):
            raise ValueError("winner_id must be one of the match participants.")

        Match.objects.filter(pk=match.pk).update(is_finished=True, winner_id=winner_id)
        match.refresh_from_db()
        return match

    @staticmethod
    @transaction.atomic
    def create_match(
        academy,
        athlete_a,
        athlete_b,
        duration_seconds: int = 300,
    ) -> Match:
        """Create a new match between two athletes in the given academy."""
        if athlete_a == athlete_b:
            raise ValueError("An athlete cannot compete against themselves.")
        return Match.objects.create(
            academy=academy,
            athlete_a=athlete_a,
            athlete_b=athlete_b,
            duration_seconds=duration_seconds,
        )
