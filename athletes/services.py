"""
Business logic for athlete profile management.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.models import Belt

from .models import AthleteProfile


@dataclass
class PromotionReadiness:
    athlete_id: int
    current_belt: str
    next_belt: Optional[str]
    requirement_found: bool
    is_ready: bool
    mat_hours_ok: bool
    mat_hours_current: float
    mat_hours_required: float
    months_ok: bool
    months_current: float
    months_required: int
    stripes_ok: bool
    stripes_current: int
    stripes_required: int


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

        from notifications.services import NotificationTriggers
        NotificationTriggers.on_stripe_award(athlete, athlete.stripes)

        if athlete.stripes == 4:
            readiness = PromotionService.evaluate(athlete)
            if readiness.is_ready:
                NotificationTriggers.on_promotion_ready(athlete)

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
            belt=new_belt, stripes=0, belt_awarded_at=timezone.now()
        )
        athlete.refresh_from_db()

        from notifications.services import NotificationTriggers
        NotificationTriggers.on_belt_promotion(athlete, new_belt)

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


class PromotionService:
    """
    Evaluates belt promotion readiness for athletes.

    Academy-specific PromotionRequirement records take precedence over global
    (academy=None) records. If no requirement exists for the next belt,
    requirement_found=False and is_ready=False.
    """

    BELT_PROGRESSION = {
        "white": "blue",
        "blue": "purple",
        "purple": "brown",
        "brown": "black",
        "black": None,
    }

    @staticmethod
    def get_requirement(athlete: AthleteProfile, next_belt: str):
        """Return the most-specific PromotionRequirement for next_belt, or None."""
        from membership.models import PromotionRequirement

        # Academy-specific first
        req = PromotionRequirement.objects.filter(
            academy=athlete.academy, belt=next_belt
        ).first()
        if req:
            return req
        # Fall back to global default
        return PromotionRequirement.objects.filter(
            academy__isnull=True, belt=next_belt
        ).first()

    @staticmethod
    def evaluate(athlete: AthleteProfile) -> PromotionReadiness:
        """Return a PromotionReadiness snapshot for the given athlete."""
        next_belt = PromotionService.BELT_PROGRESSION.get(athlete.belt)

        # Black belt — no further promotion
        if next_belt is None:
            return PromotionReadiness(
                athlete_id=athlete.pk,
                current_belt=athlete.belt,
                next_belt=None,
                requirement_found=False,
                is_ready=False,
                mat_hours_ok=True,
                mat_hours_current=athlete.mat_hours,
                mat_hours_required=0.0,
                months_ok=True,
                months_current=0.0,
                months_required=0,
                stripes_ok=True,
                stripes_current=athlete.stripes,
                stripes_required=0,
            )

        req = PromotionService.get_requirement(athlete, next_belt)

        if req is None:
            return PromotionReadiness(
                athlete_id=athlete.pk,
                current_belt=athlete.belt,
                next_belt=next_belt,
                requirement_found=False,
                is_ready=False,
                mat_hours_ok=False,
                mat_hours_current=athlete.mat_hours,
                mat_hours_required=0.0,
                months_ok=False,
                months_current=0.0,
                months_required=0,
                stripes_ok=False,
                stripes_current=athlete.stripes,
                stripes_required=4,
            )

        # Compute months at current belt
        if athlete.belt_awarded_at:
            delta = timezone.now() - athlete.belt_awarded_at
            months_current = round(delta.days / 30.44, 1)
        else:
            months_current = 0.0

        mat_hours_ok = athlete.mat_hours >= req.min_mat_hours
        months_ok = months_current >= req.min_months_at_belt
        stripes_ok = athlete.stripes >= req.min_stripes_before_promotion

        return PromotionReadiness(
            athlete_id=athlete.pk,
            current_belt=athlete.belt,
            next_belt=next_belt,
            requirement_found=True,
            is_ready=mat_hours_ok and months_ok and stripes_ok,
            mat_hours_ok=mat_hours_ok,
            mat_hours_current=athlete.mat_hours,
            mat_hours_required=req.min_mat_hours,
            months_ok=months_ok,
            months_current=months_current,
            months_required=req.min_months_at_belt,
            stripes_ok=stripes_ok,
            stripes_current=athlete.stripes,
            stripes_required=req.min_stripes_before_promotion,
        )

    @staticmethod
    def get_academy_readiness(academy_id: int) -> list[PromotionReadiness]:
        """Return promotion readiness for every athlete in the given academy."""
        athletes = AthleteProfile.objects.filter(
            academy_id=academy_id
        ).select_related("user", "academy")
        return [PromotionService.evaluate(a) for a in athletes]
