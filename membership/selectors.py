from datetime import date

from django.db.models import QuerySet

from athletes.models import AthleteProfile

from .models import MembershipPlan, Seminar, SeminarRegistration, Subscription


def get_active_subscription(athlete: AthleteProfile) -> QuerySet:
    return Subscription.objects.filter(
        athlete=athlete, status=Subscription.Status.ACTIVE
    ).select_related("plan")


def get_plans_for_academy(academy_id: int, active_only: bool = True) -> QuerySet:
    qs = MembershipPlan.objects.filter(academy_id=academy_id)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs


def get_upcoming_seminars(academy_id: int) -> QuerySet:
    return Seminar.objects.filter(
        academy_id=academy_id,
        event_date__gte=date.today(),
        status__in=[Seminar.Status.OPEN, Seminar.Status.DRAFT],
    ).order_by("event_date")


def get_registrations_for_seminar(seminar_id: int) -> QuerySet:
    return SeminarRegistration.objects.filter(seminar_id=seminar_id).select_related(
        "athlete__user"
    )
