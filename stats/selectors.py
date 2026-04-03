"""
Read-only querysets and filters for the stats domain.
"""

from __future__ import annotations

from typing import Optional

from django.db.models import QuerySet

from athletes.models import AthleteProfile

from .models import AthleteMatchStats


def get_stats_for_athlete(athlete: AthleteProfile) -> Optional[AthleteMatchStats]:
    """Return cached match stats for an athlete, or None if not computed yet."""
    return (
        AthleteMatchStats.objects.filter(athlete=athlete)
        .select_related("athlete__user")
        .first()
    )


def get_academy_leaderboard(academy_id: int, limit: int = 20) -> QuerySet:
    """Return top athletes in an academy ranked by wins, then total matches."""
    return (
        AthleteMatchStats.objects.filter(
            athlete__academy_id=academy_id,
            total_matches__gt=0,
        )
        .select_related("athlete__user", "athlete__academy")
        .order_by("-wins", "-total_matches")[:limit]
    )


def get_stats_for_academy(academy_id: int) -> QuerySet:
    """Return all stats records for athletes in an academy."""
    return (
        AthleteMatchStats.objects.filter(athlete__academy_id=academy_id)
        .select_related("athlete__user")
        .order_by("-wins")
    )
