from datetime import date

from django.db.models import QuerySet

from athletes.models import AthleteProfile

from .models import AthleteAchievement, OpenMatSession


def get_upcoming_open_mats(academy_id: int) -> QuerySet:
    return OpenMatSession.objects.filter(
        academy_id=academy_id,
        event_date__gte=date.today(),
        is_cancelled=False,
    ).order_by("event_date")


def get_achievements_for_athlete(athlete: AthleteProfile) -> QuerySet:
    return AthleteAchievement.objects.filter(athlete=athlete).select_related("achievement")
