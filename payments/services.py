"""
Stripe service layer for FlowRoll.

All Stripe API calls live here. Views never call stripe.* directly.

StripeCustomerService  — manage Stripe Customer objects
StripeSubscriptionService — Checkout Sessions for recurring plans
StripePaymentService   — one-time payments (seminars, class passes)
"""

from __future__ import annotations

import logging
from decimal import Decimal

import stripe
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# StripeCustomerService
# ---------------------------------------------------------------------------


class StripeCustomerService:
    """Create and retrieve Stripe Customer objects linked to AthleteProfile."""

    @staticmethod
    @transaction.atomic
    def get_or_create(athlete) -> str:
        """
        Return the Stripe customer ID for the athlete.

        Creates a new Stripe Customer if one does not exist yet and immediately
        writes the ID back to athlete.stripe_customer_id in the same transaction.
        """
        if athlete.stripe_customer_id:
            return athlete.stripe_customer_id

        customer = stripe.Customer.create(
            email=athlete.user.email,
            name=athlete.user.get_full_name() or athlete.user.username,
            metadata={
                "user_id": str(athlete.user_id),
                "athlete_id": str(athlete.pk),
                "academy_id": str(athlete.academy_id) if athlete.academy_id else "",
            },
        )
        # Refresh from DB inside the lock to avoid a lost-update race
        from athletes.models import AthleteProfile
        AthleteProfile.objects.filter(pk=athlete.pk).update(
            stripe_customer_id=customer["id"]
        )
        athlete.stripe_customer_id = customer["id"]
        return customer["id"]

    @staticmethod
    def sync_email(athlete) -> None:
        """Push the athlete's current email to Stripe when their account changes."""
        if not athlete.stripe_customer_id:
            return
        stripe.Customer.modify(
            athlete.stripe_customer_id,
            email=athlete.user.email,
        )

    @staticmethod
    def create_portal_session(athlete, return_url: str) -> str:
        """
        Create a Stripe Billing Portal session and return its URL.

        Athletes use the portal for self-service card updates, plan changes,
        and cancellations. Any changes they make trigger webhook events which
        the webhook handler syncs back into the local DB.
        """
        customer_id = StripeCustomerService.get_or_create(athlete)
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session["url"]


# ---------------------------------------------------------------------------
# StripeSubscriptionService
# ---------------------------------------------------------------------------


class StripeSubscriptionService:
    """Checkout Sessions and subscription lifecycle management."""

    @staticmethod
    def create_checkout_session(
        athlete, plan, success_url: str, cancel_url: str
    ) -> str:
        """
        Create a Stripe Checkout Session and return its URL.

        MONTHLY / ANNUAL  → mode="subscription" using the plan's stripe_price_id.
        CLASS_PASS / DROP_IN → mode="payment" with inline price_data (one-time).
        """
        customer_id = StripeCustomerService.get_or_create(athlete)

        recurring_types = ("MONTHLY", "ANNUAL")
        if plan.plan_type in recurring_types:
            if not plan.stripe_price_id:
                raise ValueError(
                    f"MembershipPlan '{plan.name}' has no Stripe Price. "
                    "Run management command sync_stripe_plans first."
                )
            session = stripe.checkout.Session.create(
                customer=customer_id,
                mode="subscription",
                line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "plan_id": str(plan.pk),
                    "academy_id": str(plan.academy_id),
                    "athlete_id": str(athlete.pk),
                    "purpose": "subscription",
                },
            )
        else:
            # One-time payment for class pass / drop-in
            session = stripe.checkout.Session.create(
                customer=customer_id,
                mode="payment",
                line_items=[
                    {
                        "quantity": 1,
                        "price_data": {
                            "currency": _get_academy_currency(plan.academy),
                            "unit_amount": int(plan.price * 100),  # cents
                            "product_data": {"name": plan.name},
                        },
                    }
                ],
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "plan_id": str(plan.pk),
                    "academy_id": str(plan.academy_id),
                    "athlete_id": str(athlete.pk),
                    "purpose": "one_time_plan",
                },
            )

        return session["url"]

    @staticmethod
    @transaction.atomic
    def cancel_at_period_end(subscription) -> None:
        """
        Tell Stripe to cancel the subscription at the end of the current period.

        The local status stays ACTIVE until the webhook `customer.subscription.deleted`
        fires, at which point the handler sets it to CANCELLED.
        """
        if not subscription.stripe_subscription_id:
            return
        stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            cancel_at_period_end=True,
        )

    @staticmethod
    @transaction.atomic
    def sync_from_stripe(stripe_sub: dict, plan_id: int = None, athlete_id: int = None):
        """
        Upsert a local Subscription from a Stripe subscription object.

        Called by the webhook handler when checkout completes or subscription
        status changes.
        """
        from membership.models import MembershipPlan, Subscription
        from athletes.models import AthleteProfile

        stripe_sub_id = stripe_sub["id"]
        stripe_status = stripe_sub["status"]

        # Map Stripe statuses to local statuses
        status_map = {
            "active": Subscription.Status.ACTIVE,
            "trialing": Subscription.Status.ACTIVE,
            "past_due": Subscription.Status.PAUSED,
            "paused": Subscription.Status.PAUSED,
            "canceled": Subscription.Status.CANCELLED,
            "unpaid": Subscription.Status.PAUSED,
            "incomplete": Subscription.Status.PAUSED,
            "incomplete_expired": Subscription.Status.CANCELLED,
        }
        local_status = status_map.get(stripe_status, Subscription.Status.PAUSED)

        existing = Subscription.objects.filter(
            stripe_subscription_id=stripe_sub_id
        ).first()

        if existing:
            existing.status = local_status
            existing.save(update_fields=["status"])
            return existing

        # New subscription — we need plan and athlete from metadata
        if plan_id is None or athlete_id is None:
            logger.warning(
                "sync_from_stripe called without plan_id/athlete_id for new sub %s",
                stripe_sub_id,
            )
            return None

        try:
            plan = MembershipPlan.objects.get(pk=plan_id)
            athlete = AthleteProfile.objects.get(pk=athlete_id)
        except (MembershipPlan.DoesNotExist, AthleteProfile.DoesNotExist):
            logger.error("Plan %s or athlete %s not found", plan_id, athlete_id)
            return None

        from membership.services import SubscriptionService
        sub = SubscriptionService.subscribe(athlete=athlete, plan=plan)
        sub.stripe_subscription_id = stripe_sub_id
        sub.status = local_status
        sub.save(update_fields=["stripe_subscription_id", "status"])
        return sub


# ---------------------------------------------------------------------------
# StripePaymentService
# ---------------------------------------------------------------------------


class StripePaymentService:
    """One-time payments and refunds (seminars, class passes)."""

    @staticmethod
    def create_seminar_checkout_session(
        athlete, seminar, registration, success_url: str, cancel_url: str
    ) -> str:
        """
        Create a Checkout Session for a seminar registration payment.

        The seminar registration must already exist (created by SeminarService.register).
        On payment success, the webhook flips registration.payment_status to PAID.
        """
        customer_id = StripeCustomerService.get_or_create(athlete)
        academy_currency = _get_academy_currency(seminar.academy)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="payment",
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": academy_currency,
                        "unit_amount": int(seminar.price * 100),
                        "product_data": {"name": seminar.title},
                    },
                }
            ],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "seminar_id": str(seminar.pk),
                "seminar_registration_id": str(registration.pk),
                "athlete_id": str(athlete.pk),
                "academy_id": str(seminar.academy_id),
                "purpose": "seminar",
            },
        )
        return session["url"]

    @staticmethod
    def refund_payment_intent(
        payment_intent_id: str, reason: str = "requested_by_customer"
    ) -> dict:
        """Issue a full refund for a PaymentIntent."""
        return stripe.Refund.create(
            payment_intent=payment_intent_id,
            reason=reason,
        )

    @staticmethod
    @transaction.atomic
    def handle_payment_intent_succeeded(payment_intent: dict) -> None:
        """
        Route a succeeded PaymentIntent to the correct local update.

        Reads the metadata.purpose field set when the checkout session was created
        to determine whether this is a seminar payment or a one-time plan purchase.
        """
        from membership.models import SeminarRegistration, Subscription

        metadata = payment_intent.get("metadata", {})
        purpose = metadata.get("purpose")
        pi_id = payment_intent["id"]

        if purpose == "seminar":
            reg_id = metadata.get("seminar_registration_id")
            if reg_id:
                SeminarRegistration.objects.filter(pk=reg_id).update(
                    payment_status=SeminarRegistration.PaymentStatus.PAID,
                    stripe_payment_intent_id=pi_id,
                )

        elif purpose == "one_time_plan":
            # Record the payment on the athlete's dojo tab as a credit
            athlete_id = metadata.get("athlete_id")
            academy_id = metadata.get("academy_id")
            plan_id = metadata.get("plan_id")
            if athlete_id and academy_id and plan_id:
                _record_tab_credit_for_plan(athlete_id, academy_id, plan_id, pi_id)


# ---------------------------------------------------------------------------
# Webhook event dispatcher
# ---------------------------------------------------------------------------


def dispatch_webhook_event(event: dict) -> None:
    """Route a Stripe event to the appropriate handler."""
    handlers = {
        "checkout.session.completed": _handle_checkout_completed,
        "invoice.payment_succeeded": _handle_invoice_payment_succeeded,
        "invoice.payment_failed": _handle_invoice_payment_failed,
        "customer.subscription.deleted": _handle_subscription_deleted,
        "customer.subscription.updated": _handle_subscription_updated,
        "payment_intent.succeeded": _handle_payment_intent_succeeded,
        "payment_intent.payment_failed": _handle_payment_intent_failed,
        "charge.refunded": _handle_charge_refunded,
    }
    handler = handlers.get(event["type"])
    if handler:
        handler(event["data"]["object"])
    else:
        logger.debug("Unhandled Stripe event type: %s", event["type"])


# ---------------------------------------------------------------------------
# Private event handlers
# ---------------------------------------------------------------------------


def _handle_checkout_completed(session: dict) -> None:
    metadata = session.get("metadata", {})
    purpose = metadata.get("purpose")

    if purpose == "subscription" and session.get("subscription"):
        # Store the stripe_subscription_id — the actual activation happens
        # on invoice.payment_succeeded (the authoritative money-moved event).
        from membership.models import Subscription
        stripe_sub_id = session["subscription"]
        Subscription.objects.filter(
            stripe_subscription_id=stripe_sub_id
        ).update()  # no-op if already created; sync_from_stripe handles creation

        # If subscription not yet created locally, create it now
        existing = Subscription.objects.filter(
            stripe_subscription_id=stripe_sub_id
        ).exists()
        if not existing:
            stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)
            StripeSubscriptionService.sync_from_stripe(
                stripe_sub,
                plan_id=_int(metadata.get("plan_id")),
                athlete_id=_int(metadata.get("athlete_id")),
            )


def _handle_invoice_payment_succeeded(invoice: dict) -> None:
    from membership.models import Subscription
    from membership.services import DojoTabService
    from athletes.models import AthleteProfile
    from academies.models import Academy

    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return

    try:
        sub = Subscription.objects.select_related("plan__academy", "athlete").get(
            stripe_subscription_id=stripe_sub_id
        )
    except Subscription.DoesNotExist:
        logger.warning("No local subscription found for stripe_sub_id %s", stripe_sub_id)
        return

    # Ensure subscription is marked ACTIVE
    if sub.status != Subscription.Status.ACTIVE:
        Subscription.objects.filter(pk=sub.pk).update(
            status=Subscription.Status.ACTIVE
        )

    # Record the payment as a credit on the athlete's dojo tab
    amount_paid = Decimal(str(invoice.get("amount_paid", 0))) / 100
    if amount_paid > 0:
        pi_id = invoice.get("payment_intent", "")
        tx = DojoTabService.credit(
            athlete=sub.athlete,
            academy=sub.plan.academy,
            amount=amount_paid,
            description=f"Stripe payment – {sub.plan.name}",
        )
        if pi_id:
            from membership.models import DojoTabTransaction
            DojoTabTransaction.objects.filter(pk=tx.pk).update(
                stripe_payment_intent_id=pi_id
            )


def _handle_invoice_payment_failed(invoice: dict) -> None:
    from membership.models import Subscription

    stripe_sub_id = invoice.get("subscription")
    if stripe_sub_id:
        Subscription.objects.filter(
            stripe_subscription_id=stripe_sub_id,
            status=Subscription.Status.ACTIVE,
        ).update(status=Subscription.Status.PAUSED)


def _handle_subscription_deleted(stripe_sub: dict) -> None:
    from membership.models import Subscription

    Subscription.objects.filter(
        stripe_subscription_id=stripe_sub["id"]
    ).update(status=Subscription.Status.CANCELLED)


def _handle_subscription_updated(stripe_sub: dict) -> None:
    StripeSubscriptionService.sync_from_stripe(stripe_sub)


def _handle_payment_intent_succeeded(pi: dict) -> None:
    StripePaymentService.handle_payment_intent_succeeded(pi)


def _handle_payment_intent_failed(pi: dict) -> None:
    # Log for dunning; no local state change needed at this layer
    logger.warning(
        "PaymentIntent %s failed: %s",
        pi.get("id"),
        pi.get("last_payment_error", {}).get("message", ""),
    )


def _handle_charge_refunded(charge: dict) -> None:
    from membership.models import SeminarRegistration

    pi_id = charge.get("payment_intent")
    if not pi_id:
        return

    # Update seminar registrations paid via this PaymentIntent
    SeminarRegistration.objects.filter(
        stripe_payment_intent_id=pi_id,
        payment_status=SeminarRegistration.PaymentStatus.PAID,
    ).update(payment_status=SeminarRegistration.PaymentStatus.REFUNDED)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_academy_currency(academy) -> str:
    """Return the currency configured for an academy, defaulting to USD."""
    try:
        from payments.models import StripeAcademyConfig
        config = StripeAcademyConfig.objects.get(academy=academy)
        return config.default_currency
    except Exception:
        return "usd"


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _record_tab_credit_for_plan(
    athlete_id: int, academy_id: int, plan_id: int, pi_id: str
) -> None:
    from membership.models import DojoTabTransaction, MembershipPlan
    from membership.services import DojoTabService
    from athletes.models import AthleteProfile
    from academies.models import Academy

    try:
        athlete = AthleteProfile.objects.get(pk=athlete_id)
        academy = Academy.objects.get(pk=academy_id)
        plan = MembershipPlan.objects.get(pk=plan_id)
    except Exception:
        return

    tx = DojoTabService.credit(
        athlete=athlete,
        academy=academy,
        amount=plan.price,
        description=f"Stripe payment – {plan.name}",
    )
    DojoTabTransaction.objects.filter(pk=tx.pk).update(stripe_payment_intent_id=pi_id)
