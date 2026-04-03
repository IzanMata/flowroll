"""
Business logic for statistics computation and aggregation.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count, Q, Sum

from athletes.models import AthleteProfile
from matches.models import Match, MatchEvent

from .models import AthleteMatchStats


class StatsService:
    """Computes and materialises match statistics for athletes."""

    @staticmethod
    @transaction.atomic
    def recompute_for_athlete(athlete: AthleteProfile) -> AthleteMatchStats:
        """
        Recompute all match statistics for an athlete from scratch and persist them.

        This method is called after every match is finished so that
        AthleteMatchStats always reflects the complete match history.
        Uses a single aggregated query per stat group to avoid N+1.
        """
        from django.db.models import Q

        finished_matches = Match.objects.filter(
            Q(athlete_a=athlete.user) | Q(athlete_b=athlete.user),
            is_finished=True,
        )

        totals = finished_matches.aggregate(
            total=Count("pk", distinct=True),
            wins=Count("pk", filter=Q(winner=athlete.user), distinct=True),
            draws=Count("pk", filter=Q(winner__isnull=True), distinct=True),
        )

        total_matches = totals["total"] or 0
        wins = totals["wins"] or 0
        draws = totals["draws"] or 0
        losses = max(0, total_matches - wins - draws)

        # Points scored / conceded
        points_scored = (
            MatchEvent.objects.filter(
                match__in=finished_matches,
                athlete=athlete.user,
                event_type=MatchEvent.TypeChoices.POINTS,
            ).aggregate(total=Sum("points_awarded"))["total"]
            or 0
        )

        points_conceded = (
            MatchEvent.objects.filter(
                match__in=finished_matches,
                event_type=MatchEvent.TypeChoices.POINTS,
            )
            .exclude(athlete=athlete.user)
            .aggregate(total=Sum("points_awarded"))["total"]
            or 0
        )

        # Submissions won: matches where this athlete won via SUBMISSION event
        submissions_won = MatchEvent.objects.filter(
            match__in=finished_matches,
            match__winner=athlete.user,
            athlete=athlete.user,
            event_type=MatchEvent.TypeChoices.SUBMISSION,
        ).values("match").distinct().count()

        stats, _ = AthleteMatchStats.objects.update_or_create(
            athlete=athlete,
            defaults={
                "total_matches": total_matches,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "total_points_scored": points_scored,
                "total_points_conceded": points_conceded,
                "submissions_won": submissions_won,
            },
        )
        return stats

    @staticmethod
    def get_or_create_stats(athlete: AthleteProfile) -> AthleteMatchStats:
        """Return existing stats, creating an empty record if none exists yet."""
        stats, _ = AthleteMatchStats.objects.get_or_create(
            athlete=athlete,
            defaults={
                "total_matches": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "total_points_scored": 0,
                "total_points_conceded": 0,
                "submissions_won": 0,
            },
        )
        return stats

    @staticmethod
    def get_academy_leaderboard(academy_id: int, limit: int = 20) -> list:
        """
        Return a list of AthleteMatchStats for an academy, ranked by wins descending.

        Only includes athletes with at least one match.
        """
        return list(
            AthleteMatchStats.objects.filter(
                athlete__academy_id=academy_id,
                total_matches__gt=0,
            )
            .select_related("athlete__user")
            .order_by("-wins", "-total_matches")[:limit]
        )
