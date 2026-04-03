"""
Read-only querysets and filters for the athletes domain.
"""

from __future__ import annotations

from typing import Optional

from django.db.models import Count, QuerySet

from .models import AthleteProfile


def get_athletes_for_academy(
    academy_id: int,
    belt: Optional[str] = None,
    search: Optional[str] = None,
) -> QuerySet:
    """
    Return athlete profiles for an academy, with user data pre-fetched.

    Optionally filter by belt colour or search by username/name.
    """
    qs = (
        AthleteProfile.objects.filter(academy_id=academy_id)
        .select_related("user", "academy", "coach__user")
        .annotate(total_check_ins=Count("check_ins", distinct=True))
    )
    if belt:
        qs = qs.filter(belt=belt)
    if search:
        qs = qs.filter(user__username__icontains=search)
    return qs.order_by("user__username")


def get_athlete_by_user(user_id: int) -> Optional[AthleteProfile]:
    """Return the AthleteProfile for a given user, or None if not found."""
    return (
        AthleteProfile.objects.filter(user_id=user_id)
        .select_related("user", "academy", "coach__user")
        .first()
    )


def get_top_athletes_by_mat_hours(academy_id: int, limit: int = 10) -> QuerySet:
    """Return the top N athletes in an academy ranked by mat hours."""
    return (
        AthleteProfile.objects.filter(academy_id=academy_id)
        .select_related("user")
        .order_by("-mat_hours")[:limit]
    )


def get_athlete_students(coach: AthleteProfile) -> QuerySet:
    """Return all athletes directly coached by this profile."""
    return (
        AthleteProfile.objects.filter(coach=coach)
        .select_related("user", "academy")
        .order_by("user__username")
    )


def get_athletes_ready_for_promotion(academy_id: int) -> QuerySet:
    """
    Return athletes who have 4 stripes (maximum) — likely candidates for belt promotion.
    The full readiness check is delegated to PromotionService.
    """
    return (
        AthleteProfile.objects.filter(academy_id=academy_id, stripes=4)
        .select_related("user")
        .order_by("belt", "user__username")
    )
