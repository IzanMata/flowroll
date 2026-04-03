"""
Business logic for athlete profile management.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import F

from core.models import Belt

from .models import AthleteProfile


class AthleteProfileService:
    """Handles belt promotions, stripe awards, and weight updates."""

    @staticmethod
    @transaction.atomic
    def award_stripe(athlete: AthleteProfile, awarded_by: AthleteProfile) -> AthleteProfile:
        """
        Award a stripe to an athlete (max 4 per belt).

        Raises ValueError if the athlete already has 4 stripes (should be promoted instead)
        or if the awarder is not a professor/owner.
        """
        from core.models import AcademyMembership

        if athlete.stripes >= 4:
            raise ValueError(
                "Athlete already has 4 stripes. Promote to next belt instead."
            )

        if not AcademyMembership.objects.filter(
            user=awarded_by.user,
            academy=athlete.academy,
            role__in=[AcademyMembership.Role.PROFESSOR, AcademyMembership.Role.OWNER],
            is_active=True,
        ).exists():
            raise ValueError("Only professors and owners can award stripes.")

        AthleteProfile.objects.filter(pk=athlete.pk).update(stripes=F("stripes") + 1)
        athlete.refresh_from_db()
        return athlete

    @staticmethod
    @transaction.atomic
    def promote_belt(
        athlete: AthleteProfile,
        new_belt: str,
        awarded_by: AthleteProfile,
    ) -> AthleteProfile:
        """
        Promote an athlete to a new belt, resetting stripes to 0.

        The new belt must be strictly higher in the progression order than
        the current belt. Raises ValueError on invalid progression or
        insufficient permissions.
        """
        from core.models import AcademyMembership

        belt_order = {
            Belt.BeltColor.WHITE: 1,
            Belt.BeltColor.BLUE: 2,
            Belt.BeltColor.PURPLE: 3,
            Belt.BeltColor.BROWN: 4,
            Belt.BeltColor.BLACK: 5,
        }

        if belt_order.get(new_belt, 0) <= belt_order.get(athlete.belt, 0):
            raise ValueError(
                f"Cannot promote from {athlete.belt} to {new_belt}: "
                "new belt must be higher in the progression order."
            )

        if not AcademyMembership.objects.filter(
            user=awarded_by.user,
            academy=athlete.academy,
            role__in=[AcademyMembership.Role.PROFESSOR, AcademyMembership.Role.OWNER],
            is_active=True,
        ).exists():
            raise ValueError("Only professors and owners can promote athletes.")

        AthleteProfile.objects.filter(pk=athlete.pk).update(
            belt=new_belt, stripes=0
        )
        athlete.refresh_from_db()
        return athlete

    @staticmethod
    @transaction.atomic
    def update_weight(athlete: AthleteProfile, weight_kg: float) -> AthleteProfile:
        """Update an athlete's competition weight in kilograms."""
        if weight_kg <= 0:
            raise ValueError("Weight must be a positive value.")
        AthleteProfile.objects.filter(pk=athlete.pk).update(weight=weight_kg)
        athlete.refresh_from_db()
        return athlete

    @staticmethod
    @transaction.atomic
    def assign_coach(athlete: AthleteProfile, coach: AthleteProfile) -> AthleteProfile:
        """
        Assign a coach to an athlete.

        Guards against circular references: raises ValueError if assigning
        *coach* would create a cycle in the lineage graph.
        """
        if athlete.pk == coach.pk:
            raise ValueError("An athlete cannot be their own coach.")

        # Verify no cycle: walk coach's lineage and ensure athlete is not in it
        current = coach
        visited = {athlete.pk}
        while current is not None:
            if current.pk in visited:
                raise ValueError(
                    "Assigning this coach would create a circular lineage reference."
                )
            visited.add(current.pk)
            current = current.coach

        athlete.coach = coach
        athlete.save(update_fields=["coach"])
        return athlete
