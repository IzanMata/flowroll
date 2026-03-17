from django.db.models import Count, QuerySet
from django.utils import timezone

from athletes.models import AthleteProfile

from .models import CheckIn, DropInVisitor, TrainingClass


def get_classes_for_academy(academy_id: int, upcoming_only: bool = False) -> QuerySet:
    """
    Return training classes for an academy, annotated with attendance_count.

    L-3 fix: attendance_count is computed as a single COUNT annotation at the
    DB level, eliminating the N+1 query that occurred when the serializer called
    obj.check_ins.count() per row. Pass upcoming_only=True to filter to classes
    whose scheduled_at is in the future.
    """
    # L-3 fix: annotate attendance_count once at the DB level so the serializer
    # can read obj.attendance_count without issuing a separate COUNT query per row.
    qs = (
        TrainingClass.objects.filter(academy_id=academy_id)
        .select_related("professor")
        .annotate(attendance_count=Count("check_ins", distinct=True))
    )
    if upcoming_only:
        qs = qs.filter(scheduled_at__gte=timezone.now())
    return qs


def get_check_ins_for_class(training_class_id: int) -> QuerySet:
    """Return all check-in records for a training class, ordered by check-in time."""
    return (
        CheckIn.objects.filter(training_class_id=training_class_id)
        .select_related("athlete__user")
        .order_by("checked_in_at")
    )


def get_athlete_attendance_history(athlete: AthleteProfile) -> QuerySet:
    """Return an athlete's full check-in history, newest first."""
    return (
        CheckIn.objects.filter(athlete=athlete)
        .select_related("training_class")
        .order_by("-checked_in_at")
    )


def get_class_attendance_count(training_class_id: int) -> int:
    """Return the total number of check-ins for a training class."""
    return CheckIn.objects.filter(training_class_id=training_class_id).count()


def get_active_drop_ins_for_academy(academy_id: int) -> QuerySet:
    """Return drop-in visitors with ACTIVE status whose token has not yet expired."""
    return DropInVisitor.objects.filter(
        academy_id=academy_id,
        status=DropInVisitor.Status.ACTIVE,
        expires_at__gte=timezone.now(),
    )
