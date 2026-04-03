"""
Read-only querysets and filters for the competitions domain.
"""

from __future__ import annotations

from typing import Optional

from django.db.models import Count, Q, QuerySet

from .models import Tournament, TournamentDivision, TournamentMatch, TournamentParticipant


def get_tournaments_for_academy(
    academy_id: int,
    status: Optional[str] = None,
) -> QuerySet:
    """Return tournaments for an academy, annotated with participant count."""
    qs = (
        Tournament.objects.filter(academy_id=academy_id)
        .annotate(
            participant_count=Count(
                "participants",
                filter=Q(
                    participants__status__in=[
                        TournamentParticipant.RegistrationStatus.CONFIRMED,
                        TournamentParticipant.RegistrationStatus.CHECKED_IN,
                    ]
                ),
                distinct=True,
            )
        )
        .prefetch_related("divisions")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def get_tournament_bracket(tournament_id: int) -> QuerySet:
    """Return all matches for a tournament, ordered by round, with athletes pre-fetched."""
    return (
        TournamentMatch.objects.filter(tournament_id=tournament_id)
        .select_related(
            "athlete_a__user",
            "athlete_b__user",
            "winner__user",
            "division",
        )
        .order_by("round_number", "id")
    )


def get_participants_for_tournament(
    tournament_id: int,
    division_id: Optional[int] = None,
) -> QuerySet:
    """Return confirmed participants for a tournament, optionally filtered by division."""
    qs = (
        TournamentParticipant.objects.filter(tournament_id=tournament_id)
        .exclude(status=TournamentParticipant.RegistrationStatus.WITHDRAWN)
        .select_related("athlete__user", "division")
        .order_by("seed", "athlete__user__username")
    )
    if division_id:
        qs = qs.filter(division_id=division_id)
    return qs


def get_athlete_tournament_history(athlete_id: int) -> QuerySet:
    """Return all tournament entries for an athlete, newest first."""
    return (
        TournamentParticipant.objects.filter(athlete_id=athlete_id)
        .select_related("tournament", "division")
        .order_by("-tournament__date")
    )


def get_divisions_for_tournament(tournament_id: int) -> QuerySet:
    """Return all divisions in a tournament with participant counts."""
    return (
        TournamentDivision.objects.filter(tournament_id=tournament_id)
        .annotate(
            confirmed_count=Count(
                "participants",
                filter=Q(
                    participants__status=TournamentParticipant.RegistrationStatus.CONFIRMED
                ),
                distinct=True,
            )
        )
        .order_by("name")
    )
