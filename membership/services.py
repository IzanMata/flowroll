"""
Business logic for memberships, promotions, dojo tab, and seminars.
"""

from __future__ import annotations

import stripe
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from athletes.models import AthleteProfile
from core.models import AcademyMembership

from .models import (DojoTabBalance, DojoTabTransaction, MembershipPlan,
                     PromotionRequirement, Seminar, SeminarRegistration,
                     Subscription, StripeCustomer, StripePaymentMethod,
                     StripeSubscription, StripePayment, StripeWebhookEvent,
                     StripeConnectedAccount, PlatformCommission, MarketplaceTransaction,
                     AcademyEarnings)

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
    @transaction.atomic
    def cancel(subscription: "Subscription", user) -> "Subscription":
        """
        Cancel an active subscription.

        Only the athlete who owns the subscription may cancel it.
        Raises ValueError if the subscription is not active or does not
        belong to the requesting user.
        """
        if subscription.athlete.user_id != user.pk:
            raise ValueError("You can only cancel your own subscription.")
        if subscription.status != Subscription.Status.ACTIVE:
            raise ValueError(
                f"Cannot cancel a subscription with status '{subscription.status}'."
            )
        subscription.status = Subscription.Status.CANCELLED
        subscription.save(update_fields=["status"])
        return subscription

    @staticmethod
    def expire_stale_subscriptions() -> int:
        """Mark all past end-date active subscriptions as EXPIRED."""
        return Subscription.objects.filter(
            status=Subscription.Status.ACTIVE,
            end_date__lt=date.today(),
        ).update(status=Subscription.Status.EXPIRED)


# ---------------------------------------------------------------------------
# Leave Academy Service
# ---------------------------------------------------------------------------


class LeaveAcademyService:
    """
    Handles a user voluntarily leaving an academy.

    Rules:
    - OWNER cannot leave — they must transfer ownership first to avoid
      orphaning the academy.
    - Deactivates the AcademyMembership.
    - Cancels any active subscriptions at that academy so the athlete is
      not billed for a gym they can no longer access.
    """

    @staticmethod
    @transaction.atomic
    def leave(user, academy) -> None:
        try:
            membership = AcademyMembership.objects.get(
                user=user, academy=academy, is_active=True
            )
        except AcademyMembership.DoesNotExist:
            raise ValueError("You are not an active member of this academy.")

        if membership.role == AcademyMembership.Role.OWNER:
            raise ValueError(
                "Academy owners cannot leave. Transfer ownership to another member first."
            )

        membership.is_active = False
        membership.save(update_fields=["is_active"])

        # Cancel active subscriptions at this academy
        try:
            athlete = user.profile
            Subscription.objects.filter(
                athlete=athlete,
                plan__academy=academy,
                status=Subscription.Status.ACTIVE,
            ).update(status=Subscription.Status.CANCELLED)
        except Exception:
            pass  # User may not have an AthleteProfile yet — that is fine


# ---------------------------------------------------------------------------
# Enrollment Service
# ---------------------------------------------------------------------------


class EnrollmentService:
    """
    Handles the full onboarding flow when a user joins an academy by purchasing
    a membership plan:

    1. Create (or reactivate) an AcademyMembership with STUDENT role.
    2. Create an AthleteProfile for the user if one does not exist yet.
    3. Create a Subscription to the chosen plan via SubscriptionService.
    """

    @staticmethod
    @transaction.atomic
    def enroll(user, academy, plan: MembershipPlan) -> dict:
        """
        Enroll *user* in *academy* under *plan*.

        Raises ValueError if the plan does not belong to the academy or is inactive.
        Returns a dict with keys ``membership`` and ``subscription``.
        """
        if plan.academy_id != academy.pk:
            raise ValueError("The selected plan does not belong to this academy.")
        if not plan.is_active:
            raise ValueError("The selected plan is not currently active.")

        # 1. AcademyMembership — create or reactivate
        membership, _ = AcademyMembership.objects.get_or_create(
            user=user,
            academy=academy,
            defaults={"role": AcademyMembership.Role.STUDENT, "is_active": True},
        )
        if not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=["is_active"])

        # 2. AthleteProfile — create if the user has none yet
        profile, _ = AthleteProfile.objects.get_or_create(
            user=user,
            defaults={"academy": academy},
        )

        # 3. Guard: reject if the athlete already has an active subscription at this academy
        already_subscribed = Subscription.objects.filter(
            athlete=profile,
            plan__academy=academy,
            status=Subscription.Status.ACTIVE,
        ).exists()
        if already_subscribed:
            raise ValueError(
                "You already have an active subscription at this academy. "
                "Cancel it before subscribing to a new plan."
            )

        # 4. Subscription
        subscription = SubscriptionService.subscribe(athlete=profile, plan=plan)

        return {"membership": membership, "subscription": subscription}

    @staticmethod
    @transaction.atomic
    def enroll_with_stripe(
        user,
        academy,
        plan: MembershipPlan,
        payment_method_id: Optional[str] = None,
        trial_days: int = 0
    ) -> Dict[str, Any]:
        """
        Enroll user in academy with Stripe billing for recurring plans.
        For non-recurring plans, falls back to standard enrollment.

        Returns dict with keys:
        - membership: AcademyMembership
        - subscription: Subscription (internal)
        - stripe_subscription: StripeSubscription (if applicable)
        - client_secret: for frontend payment confirmation (if needed)
        """
        # Basic enrollment validation
        if plan.academy_id != academy.pk:
            raise ValueError("The selected plan does not belong to this academy.")
        if not plan.is_active:
            raise ValueError("The selected plan is not currently active.")

        # Handle non-recurring plans with standard enrollment
        if plan.plan_type in [MembershipPlan.PlanType.CLASS_PASS, MembershipPlan.PlanType.DROP_IN]:
            result = EnrollmentService.enroll(user, academy, plan)
            return {
                **result,
                "stripe_subscription": None,
                "client_secret": None
            }

        # For recurring plans, use Stripe
        if plan.plan_type in [MembershipPlan.PlanType.MONTHLY, MembershipPlan.PlanType.ANNUAL]:
            # Create membership and athlete profile (same as standard enrollment)
            membership, _ = AcademyMembership.objects.get_or_create(
                user=user,
                academy=academy,
                defaults={"role": AcademyMembership.Role.STUDENT, "is_active": True},
            )
            if not membership.is_active:
                membership.is_active = True
                membership.save(update_fields=["is_active"])

            # Create AthleteProfile if needed
            profile, _ = AthleteProfile.objects.get_or_create(
                user=user,
                defaults={"academy": academy},
            )

            # Check for existing active subscription
            already_subscribed = Subscription.objects.filter(
                athlete=profile,
                plan__academy=academy,
                status=Subscription.Status.ACTIVE,
            ).exists()
            if already_subscribed:
                raise ValueError(
                    "You already have an active subscription at this academy. "
                    "Cancel it before subscribing to a new plan."
                )

            # Create Stripe subscription
            stripe_result = StripeSubscriptionService.create_subscription(
                user=user,
                plan=plan,
                payment_method_id=payment_method_id,
                trial_days=trial_days
            )

            return {
                "membership": membership,
                "subscription": stripe_result["subscription"],
                "stripe_subscription": stripe_result["stripe_subscription"],
                "client_secret": stripe_result.get("client_secret")
            }

        raise ValueError(f"Unsupported plan type: {plan.plan_type}")

    @staticmethod
    @transaction.atomic
    def enroll_with_marketplace(
        user,
        academy,
        plan: MembershipPlan,
        payment_method_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Enroll user with marketplace Stripe Connect payments.

        For recurring plans, creates subscription with platform commission.
        For one-time plans, creates direct marketplace payment.
        """
        # Basic enrollment validation
        if plan.academy_id != academy.pk:
            raise ValueError("The selected plan does not belong to this academy.")
        if not plan.is_active:
            raise ValueError("The selected plan is not currently active.")

        # Create membership and athlete profile
        membership, _ = AcademyMembership.objects.get_or_create(
            user=user,
            academy=academy,
            defaults={"role": AcademyMembership.Role.STUDENT, "is_active": True},
        )
        if not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=["is_active"])

        # Create AthleteProfile if needed
        profile, _ = AthleteProfile.objects.get_or_create(
            user=user,
            defaults={"academy": academy},
        )

        # Check for existing active subscription
        already_subscribed = Subscription.objects.filter(
            athlete=profile,
            plan__academy=academy,
            status=Subscription.Status.ACTIVE,
        ).exists()
        if already_subscribed:
            raise ValueError(
                "You already have an active subscription at this academy. "
                "Cancel it before subscribing to a new plan."
            )

        # Handle different plan types
        if plan.plan_type in [MembershipPlan.PlanType.CLASS_PASS, MembershipPlan.PlanType.DROP_IN]:
            # One-time marketplace payment
            marketplace_result = MarketplacePaymentService.create_marketplace_payment_intent(
                user=user,
                academy=academy,
                amount=plan.price,
                transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
                description=f"{plan.plan_type} membership: {plan.name}",
                metadata={
                    "plan_id": str(plan.id),
                    "plan_name": plan.name
                }
            )

            # Create internal subscription (will be activated after payment succeeds)
            subscription = SubscriptionService.subscribe(athlete=profile, plan=plan)

            return {
                "membership": membership,
                "subscription": subscription,
                "marketplace_transaction": marketplace_result["marketplace_transaction"],
                "client_secret": marketplace_result["client_secret"],
                "platform_fee": marketplace_result["platform_fee"],
                "academy_receives": marketplace_result["academy_receives"]
            }

        elif plan.plan_type in [MembershipPlan.PlanType.MONTHLY, MembershipPlan.PlanType.ANNUAL]:
            # TODO: Implement recurring subscription marketplace payments
            # This requires setting up subscription with destination and application fees
            # For now, fall back to standard Stripe subscriptions
            raise ValueError("Marketplace recurring subscriptions not yet implemented. Use standard Stripe enrollment.")

        else:
            raise ValueError(f"Unsupported plan type: {plan.plan_type}")


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

    @staticmethod
    @transaction.atomic
    def register_with_stripe_payment(
        athlete: AthleteProfile,
        seminar: Seminar,
        user: User
    ) -> Dict[str, Any]:
        """
        Register athlete for seminar with marketplace Stripe payment processing.

        Returns dict with:
        - registration: SeminarRegistration
        - marketplace_transaction: MarketplaceTransaction
        - platform_fee: Decimal
        - academy_receives: Decimal
        """
        # First, register for the seminar (this handles capacity checks)
        registration = SeminarService.register(athlete, seminar)

        # Create marketplace payment if seminar has a price
        marketplace_result = None
        if seminar.price > 0:
            marketplace_result = MarketplacePaymentService.create_marketplace_payment_intent(
                user=user,
                academy=seminar.academy,
                amount=seminar.price,
                transaction_type=MarketplaceTransaction.TransactionType.SEMINAR,
                description=f"Seminar registration: {seminar.title}",
                metadata={
                    "seminar_id": str(seminar.id),
                    "registration_id": str(registration.id)
                },
                seminar_registration=registration
            )

            # Update registration payment status to pending
            registration.payment_status = SeminarRegistration.PaymentStatus.PENDING
            registration.save(update_fields=["payment_status"])

        return {
            "registration": registration,
            "marketplace_transaction": marketplace_result.get("marketplace_transaction") if marketplace_result else None,
            "client_secret": marketplace_result.get("client_secret") if marketplace_result else None,
            "platform_fee": marketplace_result.get("platform_fee") if marketplace_result else Decimal("0.00"),
            "academy_receives": marketplace_result.get("academy_receives") if marketplace_result else Decimal("0.00")
        }


# ---------------------------------------------------------------------------
# Stripe Integration Services
# ---------------------------------------------------------------------------

# Initialize Stripe with API key
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', None)


class StripeCustomerService:
    """Manages Stripe customer creation and retrieval."""

    @staticmethod
    @transaction.atomic
    def get_or_create_customer(user: User) -> StripeCustomer:
        """
        Get existing StripeCustomer or create new one.
        Creates Stripe customer via API if needed.
        """
        try:
            return StripeCustomer.objects.get(user=user, is_active=True)
        except StripeCustomer.DoesNotExist:
            pass

        # Create new Stripe customer via API
        stripe_customer = stripe.Customer.create(
            email=user.email,
            name=f"{user.first_name} {user.last_name}".strip(),
            metadata={
                "user_id": str(user.id),
                "source": "flowroll"
            }
        )

        # Save to database
        customer = StripeCustomer.objects.create(
            user=user,
            stripe_customer_id=stripe_customer.id,
            is_active=True
        )

        return customer

    @staticmethod
    @transaction.atomic
    def deactivate_customer(user: User) -> None:
        """Deactivate Stripe customer (soft delete)."""
        try:
            customer = StripeCustomer.objects.get(user=user, is_active=True)
            customer.is_active = False
            customer.save(update_fields=["is_active"])
        except StripeCustomer.DoesNotExist:
            pass


class StripePaymentMethodService:
    """Manages payment methods for Stripe customers."""

    @staticmethod
    @transaction.atomic
    def attach_payment_method(
        user: User,
        payment_method_id: str,
        set_as_default: bool = False
    ) -> StripePaymentMethod:
        """
        Attach a payment method to a customer and save details locally.
        """
        customer = StripeCustomerService.get_or_create_customer(user)

        # Attach to customer via Stripe API
        payment_method = stripe.PaymentMethod.attach(
            payment_method_id,
            customer=customer.stripe_customer_id
        )

        # Extract card details
        card_data = payment_method.get("card", {})

        # Create local record
        local_pm = StripePaymentMethod.objects.create(
            stripe_customer=customer,
            stripe_payment_method_id=payment_method_id,
            payment_method_type=StripePaymentMethod.PaymentMethodType.CARD,
            last_four=card_data.get("last4", ""),
            brand=card_data.get("brand", "").lower(),
            exp_month=card_data.get("exp_month"),
            exp_year=card_data.get("exp_year"),
            is_default=set_as_default,
            is_active=True
        )

        # Set as default if requested or if it's the first payment method
        if set_as_default or not customer.payment_methods.filter(is_default=True).exists():
            StripePaymentMethodService.set_default_payment_method(user, local_pm)

        return local_pm

    @staticmethod
    @transaction.atomic
    def set_default_payment_method(user: User, payment_method: StripePaymentMethod) -> None:
        """Set a payment method as the default for a user."""
        # Unset current default
        StripePaymentMethod.objects.filter(
            stripe_customer__user=user,
            is_default=True
        ).update(is_default=False)

        # Set new default
        payment_method.is_default = True
        payment_method.save(update_fields=["is_default"])

        # Update default in Stripe
        stripe.Customer.modify(
            payment_method.stripe_customer.stripe_customer_id,
            invoice_settings={
                "default_payment_method": payment_method.stripe_payment_method_id
            }
        )

    @staticmethod
    @transaction.atomic
    def detach_payment_method(user: User, payment_method_id: str) -> None:
        """Detach and deactivate a payment method."""
        try:
            pm = StripePaymentMethod.objects.get(
                stripe_customer__user=user,
                stripe_payment_method_id=payment_method_id,
                is_active=True
            )

            # Detach from Stripe
            stripe.PaymentMethod.detach(payment_method_id)

            # Deactivate locally
            pm.is_active = False
            pm.save(update_fields=["is_active"])

        except StripePaymentMethod.DoesNotExist:
            raise ValueError("Payment method not found or already inactive.")


class StripeSubscriptionService:
    """Manages recurring billing subscriptions via Stripe."""

    @staticmethod
    @transaction.atomic
    def create_subscription(
        user: User,
        plan: MembershipPlan,
        payment_method_id: Optional[str] = None,
        trial_days: int = 0
    ) -> Dict[str, Any]:
        """
        Create a Stripe subscription for a membership plan.
        Returns dict with 'subscription' (internal) and 'stripe_subscription' objects.
        """
        if plan.plan_type not in [MembershipPlan.PlanType.MONTHLY, MembershipPlan.PlanType.ANNUAL]:
            raise ValueError("Only MONTHLY and ANNUAL plans support Stripe subscriptions.")

        customer = StripeCustomerService.get_or_create_customer(user)

        # Create price in Stripe if not exists (this could be done via admin or migration)
        # For now, we'll create it dynamically
        stripe_price = StripeSubscriptionService._get_or_create_price(plan)

        # Prepare subscription data
        subscription_data = {
            "customer": customer.stripe_customer_id,
            "items": [{"price": stripe_price.id}],
            "metadata": {
                "user_id": str(user.id),
                "academy_id": str(plan.academy_id),
                "plan_id": str(plan.id),
                "source": "flowroll"
            }
        }

        # Add payment method if provided
        if payment_method_id:
            subscription_data["default_payment_method"] = payment_method_id

        # Add trial period if specified
        if trial_days > 0:
            subscription_data["trial_period_days"] = trial_days

        # Create Stripe subscription
        stripe_subscription = stripe.Subscription.create(**subscription_data)

        # Create internal subscription
        athlete = user.profile  # Assumes user has AthleteProfile
        internal_subscription = SubscriptionService.subscribe(athlete, plan)

        # Create StripeSubscription link
        stripe_sub_record = StripeSubscription.objects.create(
            subscription=internal_subscription,
            stripe_subscription_id=stripe_subscription.id,
            stripe_customer=customer,
            academy=plan.academy,
            status=stripe_subscription.status.upper(),
            current_period_start=datetime.fromtimestamp(
                stripe_subscription.current_period_start, tz=timezone.utc
            ),
            current_period_end=datetime.fromtimestamp(
                stripe_subscription.current_period_end, tz=timezone.utc
            ),
            cancel_at_period_end=stripe_subscription.cancel_at_period_end
        )

        return {
            "subscription": internal_subscription,
            "stripe_subscription": stripe_sub_record,
            "client_secret": stripe_subscription.latest_invoice
        }

    @staticmethod
    def _get_or_create_price(plan: MembershipPlan) -> Any:
        """Create or retrieve Stripe price for a membership plan."""
        # In production, you'd typically pre-create prices
        # Here we create them dynamically for simplicity
        interval = "month" if plan.plan_type == MembershipPlan.PlanType.MONTHLY else "year"

        return stripe.Price.create(
            unit_amount=int(plan.price * 100),  # Convert to cents
            currency="usd",
            recurring={"interval": interval},
            product_data={
                "name": plan.name,
                "metadata": {
                    "academy_id": str(plan.academy_id),
                    "plan_id": str(plan.id)
                }
            },
            metadata={
                "academy_id": str(plan.academy_id),
                "plan_id": str(plan.id),
                "source": "flowroll"
            }
        )

    @staticmethod
    @transaction.atomic
    def cancel_subscription(user: User, subscription_id: int) -> StripeSubscription:
        """Cancel a Stripe subscription immediately or at period end."""
        try:
            stripe_sub = StripeSubscription.objects.get(
                subscription_id=subscription_id,
                stripe_customer__user=user,
                status__in=[StripeSubscription.Status.ACTIVE, StripeSubscription.Status.TRIALING]
            )
        except StripeSubscription.DoesNotExist:
            raise ValueError("Active subscription not found.")

        # Cancel in Stripe (at period end to avoid prorating)
        stripe.Subscription.modify(
            stripe_sub.stripe_subscription_id,
            cancel_at_period_end=True
        )

        # Update local record
        stripe_sub.cancel_at_period_end = True
        stripe_sub.save(update_fields=["cancel_at_period_end"])

        # Cancel internal subscription
        SubscriptionService.cancel(stripe_sub.subscription, user)

        return stripe_sub


class StripePaymentService:
    """Handles one-time payments via Stripe."""

    @staticmethod
    @transaction.atomic
    def create_payment_intent(
        user: User,
        amount: Decimal,
        payment_type: str,
        description: str,
        academy,
        metadata: Optional[Dict] = None,
        seminar_registration: Optional[SeminarRegistration] = None
    ) -> StripePayment:
        """
        Create a Stripe PaymentIntent for one-time payments.
        """
        customer = StripeCustomerService.get_or_create_customer(user)

        # Prepare metadata
        payment_metadata = {
            "user_id": str(user.id),
            "academy_id": str(academy.id),
            "payment_type": payment_type,
            "source": "flowroll"
        }
        if metadata:
            payment_metadata.update(metadata)

        # Create PaymentIntent in Stripe
        payment_intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Convert to cents
            currency="usd",
            customer=customer.stripe_customer_id,
            description=description,
            metadata=payment_metadata,
            automatic_payment_methods={"enabled": True}
        )

        # Create local record
        stripe_payment = StripePayment.objects.create(
            stripe_customer=customer,
            stripe_payment_intent_id=payment_intent.id,
            academy=academy,
            payment_type=payment_type,
            amount=amount,
            currency="USD",
            status=StripePayment.Status.PROCESSING,
            description=description,
            seminar_registration=seminar_registration,
            metadata=payment_metadata
        )

        return stripe_payment

    @staticmethod
    @transaction.atomic
    def process_successful_payment(payment_intent_id: str) -> Optional[StripePayment]:
        """
        Process a successful payment and execute business logic.
        Called from webhook handler.
        """
        try:
            payment = StripePayment.objects.get(
                stripe_payment_intent_id=payment_intent_id
            )
        except StripePayment.DoesNotExist:
            return None

        # Update payment status
        payment.status = StripePayment.Status.SUCCEEDED
        payment.save(update_fields=["status"])

        # Execute payment type-specific logic
        if payment.payment_type == StripePayment.PaymentType.SEMINAR:
            StripePaymentService._process_seminar_payment(payment)
        elif payment.payment_type == StripePayment.PaymentType.DOJO_TAB_CREDIT:
            StripePaymentService._process_dojo_tab_credit(payment)

        return payment

    @staticmethod
    def _process_seminar_payment(payment: StripePayment) -> None:
        """Process successful seminar payment."""
        if payment.seminar_registration:
            payment.seminar_registration.payment_status = SeminarRegistration.PaymentStatus.PAID
            payment.seminar_registration.save(update_fields=["payment_status"])

    @staticmethod
    def _process_dojo_tab_credit(payment: StripePayment) -> None:
        """Process successful dojo tab credit payment."""
        athlete = payment.stripe_customer.user.profile
        DojoTabService.credit(
            athlete=athlete,
            academy=payment.academy,
            amount=payment.amount,
            description=f"Stripe payment: {payment.description}"
        )


class StripeWebhookService:
    """Processes Stripe webhook events."""

    @staticmethod
    @transaction.atomic
    def process_webhook(event_data: Dict) -> bool:
        """
        Process a Stripe webhook event.
        Returns True if processed successfully, False if already processed.
        """
        event_id = event_data.get("id")
        event_type = event_data.get("type")

        # Check if already processed
        webhook_event, created = StripeWebhookEvent.objects.get_or_create(
            stripe_event_id=event_id,
            defaults={
                "event_type": event_type,
                "processed": False
            }
        )

        if not created and webhook_event.processed:
            return False  # Already processed

        try:
            # Process based on event type
            if event_type == "payment_intent.succeeded":
                StripeWebhookService._handle_payment_succeeded(event_data)
            elif event_type == "invoice.payment_succeeded":
                StripeWebhookService._handle_invoice_payment_succeeded(event_data)
            elif event_type == "customer.subscription.updated":
                StripeWebhookService._handle_subscription_updated(event_data)
            elif event_type == "customer.subscription.deleted":
                StripeWebhookService._handle_subscription_canceled(event_data)
            elif event_type == "account.updated":
                StripeWebhookService._handle_account_updated(event_data)
            elif event_type == "application_fee.created":
                StripeWebhookService._handle_application_fee_created(event_data)

            # Mark as processed
            webhook_event.processed = True
            webhook_event.processed_at = timezone.now()
            webhook_event.save(update_fields=["processed", "processed_at"])

            return True

        except Exception as e:
            webhook_event.error_message = str(e)
            webhook_event.save(update_fields=["error_message"])
            raise

    @staticmethod
    def _handle_payment_succeeded(event_data: Dict) -> None:
        """Handle successful one-time payment."""
        payment_intent = event_data["data"]["object"]

        # Check if it's a marketplace payment
        if payment_intent.get("metadata", {}).get("source") == "flowroll_marketplace":
            MarketplacePaymentService.process_successful_marketplace_payment(payment_intent["id"])
        else:
            StripePaymentService.process_successful_payment(payment_intent["id"])

    @staticmethod
    def _handle_invoice_payment_succeeded(event_data: Dict) -> None:
        """Handle successful subscription invoice payment."""
        invoice = event_data["data"]["object"]
        subscription_id = invoice.get("subscription")

        if subscription_id:
            try:
                stripe_sub = StripeSubscription.objects.get(
                    stripe_subscription_id=subscription_id
                )
                # Update subscription status if needed
                if stripe_sub.status in [StripeSubscription.Status.PAST_DUE, StripeSubscription.Status.UNPAID]:
                    stripe_sub.status = StripeSubscription.Status.ACTIVE
                    stripe_sub.save(update_fields=["status"])

                    # Reactivate internal subscription
                    internal_sub = stripe_sub.subscription
                    internal_sub.status = Subscription.Status.ACTIVE
                    internal_sub.save(update_fields=["status"])

            except StripeSubscription.DoesNotExist:
                pass

    @staticmethod
    def _handle_subscription_updated(event_data: Dict) -> None:
        """Handle subscription status changes."""
        subscription = event_data["data"]["object"]
        subscription_id = subscription["id"]

        try:
            stripe_sub = StripeSubscription.objects.get(
                stripe_subscription_id=subscription_id
            )

            # Update subscription details
            stripe_sub.status = subscription["status"].upper()
            stripe_sub.current_period_start = datetime.fromtimestamp(
                subscription["current_period_start"], tz=timezone.utc
            )
            stripe_sub.current_period_end = datetime.fromtimestamp(
                subscription["current_period_end"], tz=timezone.utc
            )
            stripe_sub.cancel_at_period_end = subscription["cancel_at_period_end"]

            if subscription.get("canceled_at"):
                stripe_sub.canceled_at = datetime.fromtimestamp(
                    subscription["canceled_at"], tz=timezone.utc
                )

            stripe_sub.save()

            # Sync internal subscription status
            internal_sub = stripe_sub.subscription
            if subscription["status"] in ["canceled", "unpaid"]:
                internal_sub.status = Subscription.Status.CANCELLED
            elif subscription["status"] == "past_due":
                internal_sub.status = Subscription.Status.ACTIVE  # Keep active during grace period
            else:
                internal_sub.status = Subscription.Status.ACTIVE

            internal_sub.save(update_fields=["status"])

        except StripeSubscription.DoesNotExist:
            pass

    @staticmethod
    def _handle_subscription_canceled(event_data: Dict) -> None:
        """Handle subscription cancellation."""
        subscription = event_data["data"]["object"]
        subscription_id = subscription["id"]

        try:
            stripe_sub = StripeSubscription.objects.get(
                stripe_subscription_id=subscription_id
            )

            # Update status
            stripe_sub.status = StripeSubscription.Status.CANCELED
            stripe_sub.canceled_at = timezone.now()
            stripe_sub.save()

            # Cancel internal subscription
            internal_sub = stripe_sub.subscription
            internal_sub.status = Subscription.Status.CANCELLED
            internal_sub.save(update_fields=["status"])

        except StripeSubscription.DoesNotExist:
            pass

    @staticmethod
    def _handle_account_updated(event_data: Dict) -> None:
        """Handle Stripe Connect account updates."""
        account = event_data["data"]["object"]
        account_id = account["id"]

        try:
            connected_account = StripeConnectedAccount.objects.get(
                stripe_account_id=account_id
            )

            # Sync account status
            StripeConnectService.sync_account_status(connected_account)

        except StripeConnectedAccount.DoesNotExist:
            logger.warning(f"Received account update for unknown account: {account_id}")

    @staticmethod
    def _handle_application_fee_created(event_data: Dict) -> None:
        """Handle application fee creation (platform commission)."""
        application_fee = event_data["data"]["object"]
        charge_id = application_fee.get("originating_transaction")

        if charge_id:
            try:
                # Find the marketplace transaction
                charge = stripe.Charge.retrieve(charge_id)
                payment_intent_id = charge.payment_intent

                transaction = MarketplaceTransaction.objects.get(
                    stripe_payment_intent_id=payment_intent_id
                )

                # Update application fee ID
                transaction.stripe_application_fee_id = application_fee["id"]
                transaction.save(update_fields=["stripe_application_fee_id"])

            except MarketplaceTransaction.DoesNotExist:
                logger.warning(f"No marketplace transaction found for charge: {charge_id}")
            except Exception as e:
                logger.error(f"Failed to process application fee: {e}")


# ---------------------------------------------------------------------------
# Stripe Connect (Marketplace) Services
# ---------------------------------------------------------------------------


class StripeConnectService:
    """Manages Stripe Connect accounts for marketplace functionality."""

    @staticmethod
    @transaction.atomic
    def create_connected_account(academy, country: str = "US") -> StripeConnectedAccount:
        """
        Create a Stripe Express account for an academy.
        Express accounts are the easiest for academies to set up.
        """
        # Check if academy already has a connected account
        existing = StripeConnectedAccount.objects.filter(academy=academy).first()
        if existing:
            return existing

        # Create Stripe account
        stripe_account = stripe.Account.create(
            type="express",
            country=country,
            email=academy.email,
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            business_type="company",
            company={
                "name": academy.name,
            },
            metadata={
                "academy_id": str(academy.id),
                "academy_name": academy.name,
                "source": "flowroll"
            }
        )

        # Create local record
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id=stripe_account.id,
            account_type=StripeConnectedAccount.AccountType.EXPRESS,
            status=StripeConnectedAccount.Status.PENDING,
            business_name=academy.name,
            support_email=academy.email,
            details_submitted=False,
            charges_enabled=False,
            payouts_enabled=False
        )

        return connected_account

    @staticmethod
    @transaction.atomic
    def create_onboarding_link(connected_account: StripeConnectedAccount, return_url: str, refresh_url: str) -> str:
        """
        Create an onboarding link for academy to complete Stripe setup.
        """
        account_link = stripe.AccountLink.create(
            account=connected_account.stripe_account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding",
        )

        # Update the onboarding URL
        connected_account.onboarding_url = account_link.url
        connected_account.save(update_fields=["onboarding_url"])

        return account_link.url

    @staticmethod
    @transaction.atomic
    def create_dashboard_link(connected_account: StripeConnectedAccount) -> str:
        """
        Create a login link for academy to access their Stripe dashboard.
        """
        if not connected_account.is_fully_onboarded:
            raise ValueError("Academy must complete onboarding before accessing dashboard.")

        login_link = stripe.Account.create_login_link(
            connected_account.stripe_account_id
        )

        # Update dashboard URL
        connected_account.dashboard_url = login_link.url
        connected_account.save(update_fields=["dashboard_url"])

        return login_link.url

    @staticmethod
    @transaction.atomic
    def sync_account_status(connected_account: StripeConnectedAccount) -> StripeConnectedAccount:
        """
        Sync connected account status with Stripe.
        Should be called periodically or via webhooks.
        """
        try:
            stripe_account = stripe.Account.retrieve(connected_account.stripe_account_id)

            # Update status fields
            connected_account.details_submitted = stripe_account.details_submitted
            connected_account.charges_enabled = stripe_account.charges_enabled
            connected_account.payouts_enabled = stripe_account.payouts_enabled

            # Update business info if available
            if stripe_account.business_profile:
                bp = stripe_account.business_profile
                if bp.get("name"):
                    connected_account.business_name = bp["name"]
                if bp.get("url"):
                    connected_account.business_url = bp["url"]
                if bp.get("support_email"):
                    connected_account.support_email = bp["support_email"]

            # Update overall status
            if connected_account.is_fully_onboarded:
                connected_account.status = StripeConnectedAccount.Status.ENABLED
            elif stripe_account.requirements.get("disabled_reason"):
                connected_account.status = StripeConnectedAccount.Status.RESTRICTED
            else:
                connected_account.status = StripeConnectedAccount.Status.PENDING

            connected_account.save()

        except stripe.error.StripeError as e:
            logger.error(f"Failed to sync connected account {connected_account.stripe_account_id}: {e}")
            raise

        return connected_account

    @staticmethod
    def get_connected_account_for_academy(academy) -> Optional[StripeConnectedAccount]:
        """Get connected account for academy, or None if not set up."""
        return StripeConnectedAccount.objects.filter(academy=academy).first()


class PlatformCommissionService:
    """Manages platform commission calculations and configurations."""

    @staticmethod
    def get_commission_config(academy) -> PlatformCommission:
        """
        Get active commission configuration for an academy.
        Falls back to default if no academy-specific config exists.
        """
        # Try academy-specific config first
        config = PlatformCommission.objects.filter(
            academy=academy,
            is_active=True,
            effective_from__lte=date.today()
        ).exclude(
            effective_until__lt=date.today()
        ).first()

        if config:
            return config

        # Fall back to default platform config (academy=None)
        default_config = PlatformCommission.objects.filter(
            academy__isnull=True,
            is_active=True,
            effective_from__lte=date.today()
        ).exclude(
            effective_until__lt=date.today()
        ).first()

        if default_config:
            return default_config

        # Create default 10% commission if none exists
        return PlatformCommissionService.create_default_commission()

    @staticmethod
    @transaction.atomic
    def create_default_commission() -> PlatformCommission:
        """Create default 10% commission configuration."""
        return PlatformCommission.objects.create(
            academy=None,  # Global default
            commission_type=PlatformCommission.CommissionType.PERCENTAGE,
            percentage_rate=Decimal("0.10"),  # 10%
            min_commission=Decimal("0.50"),  # Minimum 50 cents
            is_active=True
        )

    @staticmethod
    def calculate_commission(academy, amount: Decimal) -> Decimal:
        """Calculate commission for a given amount and academy."""
        config = PlatformCommissionService.get_commission_config(academy)
        return config.calculate_commission(amount)

    @staticmethod
    @transaction.atomic
    def create_academy_commission(
        academy,
        commission_type: str,
        percentage_rate: Decimal = None,
        fixed_amount: Decimal = None,
        effective_from: date = None
    ) -> PlatformCommission:
        """Create custom commission configuration for an academy."""
        return PlatformCommission.objects.create(
            academy=academy,
            commission_type=commission_type,
            percentage_rate=percentage_rate or Decimal("0.10"),
            fixed_amount=fixed_amount or Decimal("0.00"),
            effective_from=effective_from or date.today(),
            is_active=True
        )


class MarketplacePaymentService:
    """Handles marketplace payments with automatic commission splits."""

    @staticmethod
    @transaction.atomic
    def create_marketplace_payment_intent(
        user: User,
        academy,
        amount: Decimal,
        transaction_type: str,
        description: str,
        metadata: Optional[Dict] = None,
        subscription: Optional[Subscription] = None,
        seminar_registration: Optional[SeminarRegistration] = None
    ) -> Dict[str, Any]:
        """
        Create a marketplace payment intent with automatic commission calculation.
        """
        # Get connected account for academy
        connected_account = StripeConnectService.get_connected_account_for_academy(academy)
        if not connected_account or not connected_account.is_fully_onboarded:
            raise ValueError("Academy must complete Stripe setup before accepting payments.")

        # Get customer
        customer = StripeCustomerService.get_or_create_customer(user)

        # Calculate commission
        platform_fee = PlatformCommissionService.calculate_commission(academy, amount)
        net_amount = amount - platform_fee

        # Prepare metadata
        payment_metadata = {
            "user_id": str(user.id),
            "academy_id": str(academy.id),
            "transaction_type": transaction_type,
            "platform_fee": str(platform_fee),
            "source": "flowroll_marketplace"
        }
        if metadata:
            payment_metadata.update(metadata)

        # Create payment intent with destination charge
        payment_intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Convert to cents
            currency="usd",
            customer=customer.stripe_customer_id,
            description=description,
            metadata=payment_metadata,
            # Destination charge - goes directly to connected account
            transfer_data={
                "destination": connected_account.stripe_account_id,
            },
            # Platform application fee
            application_fee_amount=int(platform_fee * 100),
            automatic_payment_methods={"enabled": True}
        )

        # Create marketplace transaction record
        marketplace_transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id=payment_intent.id,
            stripe_customer=customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=transaction_type,
            status=MarketplaceTransaction.Status.PENDING,
            gross_amount=amount,
            platform_fee=platform_fee,
            net_amount=net_amount,
            currency="USD",
            subscription=subscription,
            seminar_registration=seminar_registration,
            metadata=payment_metadata
        )

        return {
            "payment_intent": payment_intent,
            "marketplace_transaction": marketplace_transaction,
            "client_secret": payment_intent.client_secret,
            "platform_fee": platform_fee,
            "academy_receives": net_amount
        }

    @staticmethod
    @transaction.atomic
    def process_successful_marketplace_payment(payment_intent_id: str) -> Optional[MarketplaceTransaction]:
        """
        Process a successful marketplace payment.
        Called from webhook handler.
        """
        try:
            transaction = MarketplaceTransaction.objects.get(
                stripe_payment_intent_id=payment_intent_id
            )
        except MarketplaceTransaction.DoesNotExist:
            logger.error(f"Marketplace transaction not found for payment intent: {payment_intent_id}")
            return None

        # Update transaction status
        transaction.status = MarketplaceTransaction.Status.COMPLETED
        transaction.save(update_fields=["status"])

        # Get payment intent from Stripe to extract fee info
        try:
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            latest_charge = payment_intent.latest_charge

            if latest_charge:
                charge = stripe.Charge.retrieve(latest_charge)

                # Update Stripe fees
                if hasattr(charge, 'balance_transaction'):
                    balance_transaction = stripe.BalanceTransaction.retrieve(
                        charge.balance_transaction
                    )
                    transaction.stripe_fee = Decimal(str(balance_transaction.fee / 100))

                # Update transfer and application fee IDs
                if hasattr(charge, 'transfer'):
                    transaction.stripe_transfer_id = charge.transfer
                if hasattr(charge, 'application_fee'):
                    transaction.stripe_application_fee_id = charge.application_fee

                # Get invoice URLs if available
                if hasattr(payment_intent, 'invoice') and payment_intent.invoice:
                    invoice = stripe.Invoice.retrieve(payment_intent.invoice)
                    transaction.customer_invoice_url = invoice.invoice_pdf

                transaction.save()

        except Exception as e:
            logger.error(f"Failed to update transaction details: {e}")

        # Update earnings analytics
        MarketplaceAnalyticsService.update_earnings_for_transaction(transaction)

        # Execute transaction type-specific logic
        if transaction.transaction_type == MarketplaceTransaction.TransactionType.SEMINAR:
            MarketplacePaymentService._process_seminar_marketplace_payment(transaction)

        return transaction

    @staticmethod
    def _process_seminar_marketplace_payment(transaction: MarketplaceTransaction) -> None:
        """Process successful marketplace seminar payment."""
        if transaction.seminar_registration:
            transaction.seminar_registration.payment_status = SeminarRegistration.PaymentStatus.PAID
            transaction.seminar_registration.save(update_fields=["payment_status"])


class MarketplaceAnalyticsService:
    """Manages earnings analytics and reporting for academies."""

    @staticmethod
    @transaction.atomic
    def update_earnings_for_transaction(transaction: MarketplaceTransaction) -> None:
        """Update monthly earnings when a transaction is completed."""
        if transaction.status != MarketplaceTransaction.Status.COMPLETED:
            return

        # Get or create earnings record for this month
        now = timezone.now()
        earnings, created = AcademyEarnings.objects.get_or_create(
            academy=transaction.academy,
            connected_account=transaction.connected_account,
            year=now.year,
            month=now.month,
            defaults={
                "total_gross": Decimal("0.00"),
                "total_platform_fees": Decimal("0.00"),
                "total_stripe_fees": Decimal("0.00"),
                "total_net": Decimal("0.00"),
                "subscription_count": 0,
                "one_time_count": 0,
                "seminar_count": 0,
                "refund_count": 0,
                "currency": transaction.currency
            }
        )

        # Update totals using F() expressions for thread safety
        AcademyEarnings.objects.filter(pk=earnings.pk).update(
            total_gross=F("total_gross") + transaction.gross_amount,
            total_platform_fees=F("total_platform_fees") + transaction.platform_fee,
            total_stripe_fees=F("total_stripe_fees") + transaction.stripe_fee,
            total_net=F("total_net") + transaction.academy_receives
        )

        # Update transaction count
        if transaction.transaction_type == MarketplaceTransaction.TransactionType.SUBSCRIPTION:
            AcademyEarnings.objects.filter(pk=earnings.pk).update(
                subscription_count=F("subscription_count") + 1
            )
        elif transaction.transaction_type == MarketplaceTransaction.TransactionType.SEMINAR:
            AcademyEarnings.objects.filter(pk=earnings.pk).update(
                seminar_count=F("seminar_count") + 1
            )
        else:
            AcademyEarnings.objects.filter(pk=earnings.pk).update(
                one_time_count=F("one_time_count") + 1
            )

    @staticmethod
    def get_academy_earnings_summary(academy, year: int = None, month: int = None) -> Dict[str, Any]:
        """Get earnings summary for an academy."""
        now = timezone.now()
        if year is None:
            year = now.year
        if month is None:
            month = now.month

        try:
            earnings = AcademyEarnings.objects.get(
                academy=academy,
                year=year,
                month=month
            )
        except AcademyEarnings.DoesNotExist:
            return {
                "total_gross": Decimal("0.00"),
                "total_platform_fees": Decimal("0.00"),
                "total_stripe_fees": Decimal("0.00"),
                "total_net": Decimal("0.00"),
                "total_transactions": 0,
                "platform_fee_rate": Decimal("0.00"),
                "year": year,
                "month": month
            }

        return {
            "total_gross": earnings.total_gross,
            "total_platform_fees": earnings.total_platform_fees,
            "total_stripe_fees": earnings.total_stripe_fees,
            "total_net": earnings.total_net,
            "total_transactions": earnings.total_transactions,
            "platform_fee_rate": earnings.platform_fee_rate,
            "subscription_count": earnings.subscription_count,
            "seminar_count": earnings.seminar_count,
            "one_time_count": earnings.one_time_count,
            "year": year,
            "month": month
        }

    @staticmethod
    def get_academy_yearly_summary(academy, year: int = None) -> Dict[str, Any]:
        """Get yearly earnings summary for an academy."""
        if year is None:
            year = timezone.now().year

        earnings_qs = AcademyEarnings.objects.filter(academy=academy, year=year)

        if not earnings_qs.exists():
            return {
                "total_gross": Decimal("0.00"),
                "total_platform_fees": Decimal("0.00"),
                "total_stripe_fees": Decimal("0.00"),
                "total_net": Decimal("0.00"),
                "total_transactions": 0,
                "year": year,
                "monthly_breakdown": []
            }

        # Aggregate yearly totals
        from django.db.models import Sum
        yearly_totals = earnings_qs.aggregate(
            total_gross=Sum("total_gross"),
            total_platform_fees=Sum("total_platform_fees"),
            total_stripe_fees=Sum("total_stripe_fees"),
            total_net=Sum("total_net"),
            subscription_count=Sum("subscription_count"),
            seminar_count=Sum("seminar_count"),
            one_time_count=Sum("one_time_count")
        )

        # Monthly breakdown
        monthly_data = list(earnings_qs.values(
            "month", "total_gross", "total_platform_fees",
            "total_stripe_fees", "total_net"
        ).order_by("month"))

        return {
            "total_gross": yearly_totals["total_gross"] or Decimal("0.00"),
            "total_platform_fees": yearly_totals["total_platform_fees"] or Decimal("0.00"),
            "total_stripe_fees": yearly_totals["total_stripe_fees"] or Decimal("0.00"),
            "total_net": yearly_totals["total_net"] or Decimal("0.00"),
            "total_transactions": (
                (yearly_totals["subscription_count"] or 0) +
                (yearly_totals["seminar_count"] or 0) +
                (yearly_totals["one_time_count"] or 0)
            ),
            "year": year,
            "monthly_breakdown": monthly_data
        }
