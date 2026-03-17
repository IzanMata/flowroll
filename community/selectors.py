from datetime import date

from django.db.models import Count, Q, QuerySet

from athletes.models import AthleteProfile

from .models import AthleteAchievement, OpenMatRSVP, OpenMatSession


def get_upcoming_open_mats(academy_id: int) -> QuerySet:
    # P1 fix: annotate going_count in SQL to eliminate N+1 (1 query instead of 1 per session)
    return (
        OpenMatSession.objects.filter(
            academy_id=academy_id,
            event_date__gte=date.today(),
            is_cancelled=False,
        )
        .annotate(
            going_count=Count(
                "rsvps",
                filter=Q(rsvps__status=OpenMatRSVP.RSVPStatus.GOING),
                distinct=True,
            )
        )
        .order_by("event_date")
    )


def get_achievements_for_athlete(athlete: AthleteProfile) -> QuerySet:
    return AthleteAchievement.objects.filter(athlete=athlete).select_related(
        "achievement"
    )
