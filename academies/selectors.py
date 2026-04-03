"""
Read-only querysets and filters for the academies domain.
"""

from __future__ import annotations

from typing import Optional

from django.db.models import Count, Q, QuerySet

from core.models import AcademyMembership

from .models import Academy


def get_academies_for_user(user_id: int) -> QuerySet:
    """Return all active academies the user belongs to, with member counts."""
    return (
        Academy.objects.filter(
            memberships__user_id=user_id,
            memberships__is_active=True,
        )
        .annotate(member_count=Count("memberships", filter=Q(memberships__is_active=True), distinct=True))
        .select_related()
        .distinct()
    )


def get_public_academies(
    search: Optional[str] = None,
    city: Optional[str] = None,
    country: Optional[str] = None,
) -> QuerySet:
    """Return active academies visible to the public, with optional filters."""
    qs = Academy.objects.filter(is_active=True).annotate(
        member_count=Count(
            "memberships", filter=Q(memberships__is_active=True), distinct=True
        )
    )
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(city__icontains=search)
            | Q(country__icontains=search)
        )
    if city:
        qs = qs.filter(city__icontains=city)
    if country:
        qs = qs.filter(country__icontains=country)
    return qs.order_by("name")


def get_members_for_academy(
    academy_id: int,
    role: Optional[str] = None,
    active_only: bool = True,
) -> QuerySet:
    """Return memberships for an academy, optionally filtered by role."""
    qs = AcademyMembership.objects.filter(academy_id=academy_id).select_related(
        "user"
    )
    if active_only:
        qs = qs.filter(is_active=True)
    if role:
        qs = qs.filter(role=role)
    return qs.order_by("role", "user__username")


def get_academy_stats(academy_id: int) -> dict:
    """Return a summary of key metrics for an academy."""
    from athletes.models import AthleteProfile
    from django.db.models import Avg, Sum

    member_count = AcademyMembership.objects.filter(
        academy_id=academy_id, is_active=True
    ).count()

    athlete_data = AthleteProfile.objects.filter(academy_id=academy_id).aggregate(
        total_mat_hours=Sum("mat_hours"),
        avg_mat_hours=Avg("mat_hours"),
        total_athletes=Count("pk"),
    )

    return {
        "member_count": member_count,
        "total_athletes": athlete_data["total_athletes"] or 0,
        "total_mat_hours": float(athlete_data["total_mat_hours"] or 0),
        "avg_mat_hours": float(athlete_data["avg_mat_hours"] or 0),
    }
