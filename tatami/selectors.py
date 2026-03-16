from django.db.models import QuerySet

from .models import Matchup, TimerPreset, TimerSession, WeightClass


def get_presets_for_academy(academy_id: int) -> QuerySet:
    return TimerPreset.objects.filter(academy_id=academy_id)


def get_active_sessions(academy_id: int) -> QuerySet:
    return TimerSession.objects.filter(
        preset__academy_id=academy_id,
        status__in=[TimerSession.Status.RUNNING, TimerSession.Status.PAUSED],
    ).select_related("preset")


def get_matchups_for_academy(academy_id: int, match_format: str = None) -> QuerySet:
    qs = Matchup.objects.filter(academy_id=academy_id).select_related(
        "athlete_a__user", "athlete_b__user", "weight_class", "winner__user"
    )
    if match_format:
        qs = qs.filter(match_format=match_format)
    return qs
