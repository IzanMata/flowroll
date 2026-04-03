"""
Read-only querysets and filters for the matches domain.
"""

from __future__ import annotations

from typing import Optional

from django.db.models import Count, QuerySet

from .models import Match, MatchEvent


def get_matches_for_academy(
    academy_id: int,
    finished: Optional[bool] = None,
) -> QuerySet:
    """
    Return matches scoped to an academy, with athletes and events pre-fetched.

    Pass finished=True/False to filter by match state, or None to return all.
    """
    qs = (
        Match.objects.filter(academy_id=academy_id)
        .select_related("athlete_a", "athlete_b", "winner")
        .prefetch_related("events")
        .annotate(event_count=Count("events", distinct=True))
    )
    if finished is not None:
        qs = qs.filter(is_finished=finished)
    return qs


def get_match_detail(match_pk: int) -> Match:
    """Return a single match with all related data pre-fetched."""
    return (
        Match.objects.select_related("athlete_a", "athlete_b", "winner", "academy")
        .prefetch_related("events__athlete")
        .get(pk=match_pk)
    )


def get_events_for_match(match_pk: int) -> QuerySet:
    """Return all events for a match in chronological order."""
    return (
        MatchEvent.objects.filter(match_id=match_pk)
        .select_related("athlete")
        .order_by("timestamp")
    )


def get_matches_for_athlete(user_id: int) -> QuerySet:
    """Return all matches (finished or not) where the user participated."""
    return (
        Match.objects.filter(
            athlete_a_id=user_id,
        )
        | Match.objects.filter(athlete_b_id=user_id)
    ).select_related("athlete_a", "athlete_b", "winner", "academy").order_by("-date")


def get_athlete_win_count(user_id: int, academy_id: Optional[int] = None) -> int:
    """Return the number of finished matches this athlete has won."""
    qs = Match.objects.filter(winner_id=user_id, is_finished=True)
    if academy_id:
        qs = qs.filter(academy_id=academy_id)
    return qs.count()


def get_athlete_match_count(user_id: int, academy_id: Optional[int] = None) -> int:
    """Return total finished matches for an athlete."""
    from django.db.models import Q

    qs = Match.objects.filter(
        Q(athlete_a_id=user_id) | Q(athlete_b_id=user_id),
        is_finished=True,
    )
    if academy_id:
        qs = qs.filter(academy_id=academy_id)
    return qs.count()
