"""
Read-only aggregation selectors for the Academy Analytics Dashboard.

All functions return plain dicts (not querysets) because the dashboard
view serializes everything in one shot. Each selector uses a minimal
number of DB queries — no N+1 loops.

reference_date defaults to today and is accepted as a parameter so that
tests can pin time without monkey-patching timezone.now().
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Count, DecimalField, FloatField, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


# ─── helpers ──────────────────────────────────────────────────────────────────


def _month_range(ref: date):
    """Return (first_day, last_day) of the month containing ref (as date objects)."""
    first = ref.replace(day=1)
    if ref.month == 12:
        last = ref.replace(day=31)
    else:
        last = ref.replace(month=ref.month + 1, day=1) - timedelta(days=1)
    return first, last


def _prev_month_range(ref: date):
    first_this = ref.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    return _month_range(last_prev)


def _week_range(ref: date):
    """Return (monday, sunday) of the ISO week containing ref."""
    monday = ref - timedelta(days=ref.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _prev_week_range(ref: date):
    monday, _ = _week_range(ref)
    prev_monday = monday - timedelta(weeks=1)
    prev_sunday = prev_monday + timedelta(days=6)
    return prev_monday, prev_sunday


def _change_percent(current: float, previous: float) -> Optional[float]:
    """Return percentage change vs previous, or None when previous is 0."""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


# ─── Revenue ──────────────────────────────────────────────────────────────────


def get_revenue_summary(academy_id: int, ref: Optional[date] = None) -> dict:
    """
    Aggregate Payment totals for the current and previous calendar months.

    Returns:
        current_month, previous_month (Decimal strings),
        change_percent (float | None),
        currency (most common currency in current month, or "eur"),
        by_type (dict payment_type → Decimal string),
        top_currency (str).
    """
    from payments.models import Payment

    ref = ref or timezone.localdate()
    cur_start, cur_end = _month_range(ref)
    prev_start, prev_end = _prev_month_range(ref)

    base_qs = Payment.objects.filter(
        academy_id=academy_id,
        status=Payment.Status.SUCCEEDED,
    )

    cur_qs = base_qs.filter(created_at__date__gte=cur_start, created_at__date__lte=cur_end)
    prev_qs = base_qs.filter(created_at__date__gte=prev_start, created_at__date__lte=prev_end)

    zero = Decimal("0.00")
    cur_total = cur_qs.aggregate(
        total=Coalesce(Sum("amount_paid"), zero, output_field=DecimalField())
    )["total"]
    prev_total = prev_qs.aggregate(
        total=Coalesce(Sum("amount_paid"), zero, output_field=DecimalField())
    )["total"]

    # Breakdown by payment type for current month
    by_type_qs = (
        cur_qs.values("payment_type")
        .annotate(total=Coalesce(Sum("amount_paid"), zero, output_field=DecimalField()))
    )
    by_type = {row["payment_type"]: str(row["total"]) for row in by_type_qs}

    # Dominant currency (most frequent in current month)
    currency_row = (
        cur_qs.values("currency")
        .annotate(cnt=Count("pk"))
        .order_by("-cnt")
        .first()
    )
    currency = currency_row["currency"] if currency_row else "eur"

    return {
        "current_month": str(cur_total),
        "previous_month": str(prev_total),
        "change_percent": _change_percent(float(cur_total), float(prev_total)),
        "currency": currency,
        "by_type": by_type,
    }


# ─── Attendance ───────────────────────────────────────────────────────────────


def get_attendance_summary(academy_id: int, ref: Optional[date] = None) -> dict:
    """
    Aggregate CheckIn counts for the current and previous ISO weeks,
    plus total mat hours for the current month and most popular class type.
    """
    from attendance.models import CheckIn, TrainingClass

    ref = ref or timezone.localdate()
    cur_mon, cur_sun = _week_range(ref)
    prev_mon, prev_sun = _prev_week_range(ref)
    month_start, month_end = _month_range(ref)

    # CheckIns use `checked_in_at` (auto_now_add)
    academy_checkins = CheckIn.objects.filter(training_class__academy_id=academy_id)

    this_week = academy_checkins.filter(
        checked_in_at__date__gte=cur_mon,
        checked_in_at__date__lte=cur_sun,
    ).count()

    last_week = academy_checkins.filter(
        checked_in_at__date__gte=prev_mon,
        checked_in_at__date__lte=prev_sun,
    ).count()

    # Mat hours: sum of (duration_minutes/60) for classes this month that had check-ins
    month_classes = TrainingClass.objects.filter(
        academy_id=academy_id,
        scheduled_at__date__gte=month_start,
        scheduled_at__date__lte=month_end,
    )
    mat_hours_this_month = sum(
        tc.duration_minutes / 60.0
        for tc in month_classes.filter(check_ins__isnull=False).distinct()
    ) if month_classes.exists() else 0.0

    # Most popular class type this month
    popular = (
        CheckIn.objects.filter(
            training_class__academy_id=academy_id,
            checked_in_at__date__gte=month_start,
            checked_in_at__date__lte=month_end,
        )
        .values("training_class__class_type")
        .annotate(cnt=Count("pk"))
        .order_by("-cnt")
        .first()
    )
    most_popular_class_type = popular["training_class__class_type"] if popular else None

    return {
        "this_week": this_week,
        "last_week": last_week,
        "change_percent": _change_percent(this_week, last_week),
        "mat_hours_this_month": round(mat_hours_this_month, 1),
        "most_popular_class_type": most_popular_class_type,
    }


# ─── Members ──────────────────────────────────────────────────────────────────


def get_member_summary(academy_id: int) -> dict:
    """
    Return total active members, belt distribution, and athletes ready
    for promotion (4 stripes — belt promotion threshold).
    """
    from athletes.models import AthleteProfile
    from athletes.selectors import get_athletes_ready_for_promotion
    from core.models import AcademyMembership

    total_active = AcademyMembership.objects.filter(
        academy_id=academy_id,
        is_active=True,
    ).count()

    # Belt distribution (only athletes in this academy)
    belt_rows = (
        AthleteProfile.objects.filter(academy_id=academy_id)
        .values("belt")
        .annotate(count=Count("pk"))
        .order_by("belt")
    )
    belt_distribution = {row["belt"]: row["count"] for row in belt_rows}

    ready_for_promotion = get_athletes_ready_for_promotion(academy_id).count()

    return {
        "total_active": total_active,
        "ready_for_promotion": ready_for_promotion,
        "belt_distribution": belt_distribution,
    }


# ─── Membership retention ─────────────────────────────────────────────────────


def get_retention_summary(academy_id: int, ref: Optional[date] = None) -> dict:
    """
    Return active subscription count, cancellations this month, and churn rate.
    Churn rate = cancelled_this_month / (active + cancelled_this_month) * 100.
    """
    from membership.models import Subscription

    ref = ref or timezone.localdate()
    month_start, month_end = _month_range(ref)

    academy_subs = Subscription.objects.filter(athlete__academy_id=academy_id)

    active = academy_subs.filter(status=Subscription.Status.ACTIVE).count()

    cancelled_this_month = academy_subs.filter(
        status=Subscription.Status.CANCELLED,
        updated_at__date__gte=month_start,
        updated_at__date__lte=month_end,
    ).count()

    denominator = active + cancelled_this_month
    churn_rate = round(cancelled_this_month / denominator * 100, 1) if denominator else 0.0

    return {
        "active_subscriptions": active,
        "cancelled_this_month": cancelled_this_month,
        "churn_rate": churn_rate,
    }


# ─── Top athletes ─────────────────────────────────────────────────────────────


def get_top_athletes_summary(academy_id: int, limit: int = 5) -> list:
    """
    Return top N athletes by mat hours as a list of plain dicts.
    """
    from athletes.selectors import get_top_athletes_by_mat_hours

    qs = get_top_athletes_by_mat_hours(academy_id, limit=limit)
    return [
        {
            "athlete_id": a.pk,
            "username": a.user.username,
            "full_name": f"{a.user.first_name} {a.user.last_name}".strip() or a.user.username,
            "belt": a.belt,
            "stripes": a.stripes,
            "mat_hours": round(a.mat_hours, 1),
        }
        for a in qs
    ]


# ─── Full dashboard ───────────────────────────────────────────────────────────


def get_academy_dashboard(academy_id: int, ref: Optional[date] = None) -> dict:
    """
    Assemble the full dashboard payload. Each sub-section calls its own
    selector so failures are isolated and sections can be extended independently.
    """
    ref = ref or timezone.localdate()
    return {
        "academy_id": academy_id,
        "generated_at": timezone.now().isoformat(),
        "period_ref": str(ref),
        "revenue": get_revenue_summary(academy_id, ref),
        "attendance": get_attendance_summary(academy_id, ref),
        "members": get_member_summary(academy_id),
        "retention": get_retention_summary(academy_id, ref),
        "top_athletes": get_top_athletes_summary(academy_id),
    }
