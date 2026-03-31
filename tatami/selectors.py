from typing import Optional

from django.db.models import QuerySet

from .models import Matchup, TimerPreset, TimerSession


def get_presets_for_academy(academy_id: Optional[int]) -> QuerySet:
    if not academy_id:
        return TimerPreset.objects.none()
    return TimerPreset.objects.filter(academy_id=academy_id)


def get_active_sessions(academy_id: Optional[int]) -> QuerySet:
    if not academy_id:
        return TimerSession.objects.none()
    return TimerSession.objects.filter(
        preset__academy_id=academy_id,
        status__in=[TimerSession.Status.RUNNING, TimerSession.Status.PAUSED],
    ).select_related("preset")


def get_matchups_for_academy(academy_id: Optional[int], match_format: str = None) -> QuerySet:
    if not academy_id:
        return Matchup.objects.none()
    qs = Matchup.objects.filter(academy_id=academy_id).select_related(
        "athlete_a__user", "athlete_b__user", "weight_class", "winner__user"
    )
    if match_format:
        qs = qs.filter(match_format=match_format)
    return qs
