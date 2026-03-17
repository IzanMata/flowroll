"""
Business logic for memberships, promotions, dojo tab, and seminars.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import F

from athletes.models import AthleteProfile

from .models import (DojoTabBalance, DojoTabTransaction, MembershipPlan,
                     PromotionRequirement, Seminar, SeminarRegistration,
                     Subscription)

# ---------------------------------------------------------------------------
# Subscription Service
# ---------------------------------------------------------------------------


class SubscriptionService:
    @staticmethod
    @transaction.atomic
    def subscribe(
        athlete: AthleteProfile, plan: MembershipPlan, start_date: date = None
    ) -> Subscription:
        """Create and activate a new subscription for an athlete."""
        today = start_date or date.today()
        end_date = None
        if plan.duration_days:
            from datetime import timedelta

            end_date = today + timedelta(days=plan.duration_days)

        classes_remaining = plan.class_limit  # None for unlimited

        subscription = Subscription.objects.create(
            athlete=athlete,
            plan=plan,
            start_date=today,
            end_date=end_date,
            status=Subscription.Status.ACTIVE,
            classes_remaining=classes_remaining,
        )
        return subscription

    @staticmethod
    @transaction.atomic
    def consume_class_pass(subscription: Subscription) -> Subscription:
        """Decrement a class-pass subscription. Marks as EXPIRED when exhausted."""
        if subscription.plan.plan_type != MembershipPlan.PlanType.CLASS_PASS:
            raise ValueError(
                "consume_class_pass only applies to CLASS_PASS subscriptions."
            )
        if subscription.classes_remaining is None:
            raise ValueError("This class pass has unlimited classes.")
        if subscription.classes_remaining <= 0:
            raise ValueError("No classes remaining on this pass.")

        subscription.classes_remaining -= 1
        if subscription.classes_remaining == 0:
            subscription.status = Subscription.Status.EXPIRED
        subscription.save(update_fields=["classes_remaining", "status"])
        return subscription

    @staticmethod
    def expire_stale_subscriptions() -> int:
        """Mark all past end-date active subscriptions as EXPIRED."""
        return Subscription.objects.filter(
            status=Subscription.Status.ACTIVE,
            end_date__lt=date.today(),
        ).update(status=Subscription.Status.EXPIRED)


# ---------------------------------------------------------------------------
# Promotion Service
# ---------------------------------------------------------------------------


@dataclass
class PromotionReadiness:
    """
    The result of checking whether an athlete is ready for promotion.

    Attributes
    ----------
    is_ready : bool
        True if ALL requirements are satisfied.
    mat_hours_ok : bool
    months_at_belt_ok : bool
    stripes_ok : bool
    current_mat_hours : float
    required_mat_hours : float
    current_months : int
    required_months : int
    current_stripes : int
    required_stripes : int
    message : str
        Human-readable summary.
    """

    is_ready: bool
    mat_hours_ok: bool
    months_at_belt_ok: bool
    stripes_ok: bool
    current_mat_hours: float
    required_mat_hours: float
    current_months: int
    required_months: int
    current_stripes: int
    required_stripes: int
    message: str


class PromotionService:
    """
    Cross-references an athlete's training record against PromotionRequirements
    to determine whether they are eligible for a stripe or belt promotion.
    """

    @staticmethod
    def check_readiness(
        athlete: AthleteProfile,
        belt_awarded_date: Optional[date] = None,
        academy_id: Optional[int] = None,
    ) -> PromotionReadiness:
        """
        Evaluate promotion readiness for *athlete*.

        Parameters
        ----------
        athlete : AthleteProfile
        belt_awarded_date : date, optional
            The date the athlete received their current belt. Used to compute
            months at belt. Defaults to today (conservative — 0 months).
        academy_id : int, optional
            If provided, looks for academy-specific requirements first,
            falling back to the global (academy=None) requirement.
        """
        requirement = PromotionService._get_requirement(athlete.belt, academy_id)
        if requirement is None:
            return PromotionReadiness(
                is_ready=False,
                mat_hours_ok=False,
                months_at_belt_ok=False,
                stripes_ok=False,
                current_mat_hours=athlete.mat_hours,
                required_mat_hours=0.0,
                current_months=0,
                required_months=0,
                current_stripes=athlete.stripes,
                required_stripes=4,
                message=f"No promotion requirements configured for {athlete.belt} belt.",
            )

        months_at_belt = PromotionService._compute_months_at_belt(belt_awarded_date)

        mat_hours_ok = athlete.mat_hours >= requirement.min_mat_hours
        months_ok = months_at_belt >= requirement.min_months_at_belt
        stripes_ok = athlete.stripes >= requirement.min_stripes_before_promotion

        is_ready = mat_hours_ok and months_ok and stripes_ok

        if is_ready:
            message = f"{athlete} meets all requirements for promotion from {athlete.belt} belt."
        else:
            gaps = []
            if not mat_hours_ok:
                gaps.append(
                    f"mat hours: {athlete.mat_hours:.1f}/{requirement.min_mat_hours:.1f}"
                )
            if not months_ok:
                gaps.append(
                    f"months at belt: {months_at_belt}/{requirement.min_months_at_belt}"
                )
            if not stripes_ok:
                gaps.append(
                    f"stripes: {athlete.stripes}/{requirement.min_stripes_before_promotion}"
                )
            message = f"Not yet eligible. Gaps: {', '.join(gaps)}."

        return PromotionReadiness(
            is_ready=is_ready,
            mat_hours_ok=mat_hours_ok,
            months_at_belt_ok=months_ok,
            stripes_ok=stripes_ok,
            current_mat_hours=athlete.mat_hours,
            required_mat_hours=requirement.min_mat_hours,
            current_months=months_at_belt,
            required_months=requirement.min_months_at_belt,
            current_stripes=athlete.stripes,
            required_stripes=requirement.min_stripes_before_promotion,
            message=message,
        )

    @staticmethod
    def _get_requirement(
        belt: str, academy_id: Optional[int]
    ) -> Optional[PromotionRequirement]:
        """Look up academy-specific requirement first, then fall back to global."""
        if academy_id:
            req = PromotionRequirement.objects.filter(
                belt=belt, academy_id=academy_id
            ).first()
            if req:
                return req
        return PromotionRequirement.objects.filter(
            belt=belt, academy__isnull=True
        ).first()

    @staticmethod
    def _compute_months_at_belt(belt_awarded_date: Optional[date]) -> int:
        if belt_awarded_date is None:
            return 0
        today = date.today()
        return (today.year - belt_awarded_date.year) * 12 + (
            today.month - belt_awarded_date.month
        )


# ---------------------------------------------------------------------------
# Dojo Tab Service
# ---------------------------------------------------------------------------


class DojoTabService:
    """Handles micro-transactions on an athlete's internal academy credit tab."""

    @staticmethod
    @transaction.atomic
    def charge(
        athlete: AthleteProfile, academy, amount: Decimal, description: str
    ) -> DojoTabTransaction:
        """Debit the athlete's tab."""
        tx = DojoTabTransaction.objects.create(
            athlete=athlete,
            academy=academy,
            transaction_type=DojoTabTransaction.TransactionType.DEBIT,
            amount=amount,
            description=description,
        )
        DojoTabService._update_balance(athlete, academy, -amount)
        return tx

    @staticmethod
    @transaction.atomic
    def credit(
        athlete: AthleteProfile, academy, amount: Decimal, description: str
    ) -> DojoTabTransaction:
        """Credit the athlete's tab (e.g. payment received)."""
        tx = DojoTabTransaction.objects.create(
            athlete=athlete,
            academy=academy,
            transaction_type=DojoTabTransaction.TransactionType.CREDIT,
            amount=amount,
            description=description,
        )
        DojoTabService._update_balance(athlete, academy, amount)
        return tx

    @staticmethod
    def get_balance(athlete: AthleteProfile, academy) -> Decimal:
        balance, _ = DojoTabBalance.objects.get_or_create(
            athlete=athlete, academy=academy, defaults={"balance": Decimal("0.00")}
        )
        return balance.balance

    @staticmethod
    def _update_balance(athlete: AthleteProfile, academy, delta: Decimal) -> None:
        # M-5 fix: use get_or_create + F() expression to avoid the lost-update
        # race condition that occurs when two transactions read the same balance
        # concurrently and both apply an arithmetic delta from their local copy.
        DojoTabBalance.objects.get_or_create(
            athlete=athlete, academy=academy, defaults={"balance": Decimal("0.00")}
        )
        DojoTabBalance.objects.filter(athlete=athlete, academy=academy).update(
            balance=F("balance") + delta
        )


# ---------------------------------------------------------------------------
# Seminar Service
# ---------------------------------------------------------------------------


class SeminarService:
    @staticmethod
    @transaction.atomic
    def register(athlete: AthleteProfile, seminar: Seminar) -> SeminarRegistration:
        """
        Register an athlete for a seminar.
        Automatically waitlists if the seminar is full.
        """
        # M-6 fix: re-fetch the seminar with a row-level lock inside the
        # atomic block so two concurrent registrations cannot both see
        # spots_remaining > 0 and both be confirmed (overbooking).
        seminar = Seminar.objects.select_for_update().get(pk=seminar.pk)

        if seminar.status not in (Seminar.Status.OPEN, Seminar.Status.FULL):
            raise ValueError(f"Seminar '{seminar.title}' is not open for registration.")

        existing = (
            SeminarRegistration.objects.filter(seminar=seminar, athlete=athlete)
            .exclude(status=SeminarRegistration.RegistrationStatus.CANCELLED)
            .first()
        )
        if existing:
            raise ValueError("Athlete is already registered for this seminar.")

        if seminar.spots_remaining > 0:
            reg_status = SeminarRegistration.RegistrationStatus.CONFIRMED
        else:
            reg_status = SeminarRegistration.RegistrationStatus.WAITLISTED

        registration = SeminarRegistration.objects.create(
            seminar=seminar,
            athlete=athlete,
            status=reg_status,
        )

        # Mark seminar as FULL if no spots remain after this registration
        if seminar.spots_remaining == 0:
            Seminar.objects.filter(pk=seminar.pk).update(status=Seminar.Status.FULL)

        return registration

    @staticmethod
    @transaction.atomic
    def cancel_registration(registration: SeminarRegistration) -> SeminarRegistration:
        registration.status = SeminarRegistration.RegistrationStatus.CANCELLED
        registration.save(update_fields=["status"])

        # Promote the first waitlisted athlete
        waitlisted = (
            SeminarRegistration.objects.filter(
                seminar=registration.seminar,
                status=SeminarRegistration.RegistrationStatus.WAITLISTED,
            )
            .order_by("created_at")
            .first()
        )
        if waitlisted:
            waitlisted.status = SeminarRegistration.RegistrationStatus.CONFIRMED
            waitlisted.save(update_fields=["status"])
            Seminar.objects.filter(pk=registration.seminar_id).update(
                status=Seminar.Status.OPEN
            )
        return registration
