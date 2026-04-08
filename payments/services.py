"""
Stripe Connect Express service layer for FlowRoll.

Payment flow (destination charges):
1. Platform creates a PaymentIntent/Checkout Session with:
     application_fee_amount  → FlowRoll's commission (stays on platform)
     transfer_data.destination → academy's Express account ID (acct_...)
2. Stripe processes the card, keeps its own fee, transfers the net to the academy.
3. Stripe fires payment_intent.succeeded → webhook creates a local Payment record.
4. Frontend reads Payment records from DB — never queries Stripe in real time.

Connect account lifecycle:
    Academy owner POST /api/v1/payments/academy-onboarding/
    → StripeConnectExpressService.create_account_and_onboarding_link()
    → Returns onboarding_url to redirect to Stripe Express onboarding
    → After completion Stripe fires account.updated with charges_enabled=True
    → Webhook updates StripeAcademyConfig

Never call Stripe API from a view or selector. All Stripe calls live here.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Platform fee helper
# ---------------------------------------------------------------------------


def _platform_fee_percent() -> float:
    """Configurable platform commission rate (default 10 %)."""
    return float(getattr(settings, "STRIPE_PLATFORM_FEE_PERCENT", 10.0))


def _compute_fee_cents(amount_cents: int) -> int:
    """Return the platform application_fee_amount in cents."""
    return round(amount_cents * _platform_fee_percent() / 100)


def _academy_currency(academy) -> str:
    """Return the academy's configured currency (defaults to 'eur')."""
    try:
        from payments.models import StripeAcademyConfig
        cfg = StripeAcademyConfig.objects.get(academy=academy)
        return cfg.default_currency
    except Exception:
        return "eur"


def _connect_account_id(academy) -> str | None:
    """Return the academy's Stripe Connect account ID, or None if not onboarded."""
    try:
        from payments.models import StripeAcademyConfig
        cfg = StripeAcademyConfig.objects.get(academy=academy)
        return cfg.stripe_connect_account_id or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# StripeConnectExpressService
# ---------------------------------------------------------------------------


class StripeConnectExpressService:
    """Manage Stripe Connect Express accounts for academies."""

    @staticmethod
    @transaction.atomic
    def create_account_and_onboarding_link(
        academy, refresh_url: str, return_url: str
    ) -> str:
        """
        Create (or retrieve) the academy's Express account and return an
        onboarding URL for the academy owner to complete KYC on Stripe.

        If the account already exists but onboarding is incomplete, a new
        AccountLink is generated (links expire after 24 h).
        """
        from payments.models import StripeAcademyConfig

        config, _ = StripeAcademyConfig.objects.get_or_create(
            academy=academy,
            defaults={"default_currency": "eur"},
        )

        if not config.stripe_connect_account_id:
            # Create a new Express account
            account = stripe.Account.create(
                type="express",
                country=academy.country[:2].upper() if len(academy.country) >= 2 else "ES",
                email=academy.email or None,
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
                metadata={
                    "academy_id": str(academy.pk),
                    "academy_name": academy.name,
                },
            )
            StripeAcademyConfig.objects.filter(pk=config.pk).update(
                stripe_connect_account_id=account["id"]
            )
            config.stripe_connect_account_id = account["id"]

        # Always generate a fresh AccountLink (they expire)
        link = stripe.AccountLink.create(
            account=config.stripe_connect_account_id,
            type="account_onboarding",
            refresh_url=refresh_url,
            return_url=return_url,
        )
        return link["url"]

    @staticmethod
    def create_login_link(academy) -> str:
        """
        Return a Stripe Express Dashboard login URL so the academy owner can
        see their payouts, transaction history, and issued invoices.
        """
        account_id = _connect_account_id(academy)
        if not account_id:
            raise ValueError("Academy has not completed Stripe onboarding.")

        link = stripe.Account.create_login_link(account_id)
        return link["url"]

    @staticmethod
    @transaction.atomic
    def sync_account_status(stripe_account: dict) -> None:
        """
        Update the local StripeAcademyConfig from a Stripe Account object.
        Called by the account.updated webhook.
        """
        from payments.models import StripeAcademyConfig

        account_id = stripe_account["id"]
        charges_enabled = stripe_account.get("charges_enabled", False)
        payouts_enabled = stripe_account.get("payouts_enabled", False)
        details_submitted = stripe_account.get("details_submitted", False)

        updated = StripeAcademyConfig.objects.filter(
            stripe_connect_account_id=account_id
        ).update(
            charges_enabled=charges_enabled,
            payouts_enabled=payouts_enabled,
            details_submitted=details_submitted,
            onboarding_completed_at=(
                timezone.now() if charges_enabled else None
            ),
        )
        if not updated:
            logger.warning(
                "account.updated for unknown Connect account %s", account_id
            )

    @staticmethod
    def get_account_status(academy) -> dict:
        """Return a dict describing the academy's Connect account status."""
        from payments.models import StripeAcademyConfig

        try:
            config = StripeAcademyConfig.objects.get(academy=academy)
        except StripeAcademyConfig.DoesNotExist:
            return {"status": "not_connected", "charges_enabled": False, "payouts_enabled": False}

        if not config.stripe_connect_account_id:
            return {"status": "not_connected", "charges_enabled": False, "payouts_enabled": False}

        return {
            "status": "active" if config.charges_enabled else "pending_verification",
            "charges_enabled": config.charges_enabled,
            "payouts_enabled": config.payouts_enabled,
            "details_submitted": config.details_submitted,
        }


# ---------------------------------------------------------------------------
# StripeCustomerService
# ---------------------------------------------------------------------------


class StripeCustomerService:
    """Create and retrieve Stripe Customer objects linked to AthleteProfile."""

    @staticmethod
    @transaction.atomic
    def get_or_create(athlete) -> str:
        """
        Return the Stripe customer ID for the athlete, creating one if needed.
        Writes the ID back to athlete.stripe_customer_id in the same transaction.
        """
        if athlete.stripe_customer_id:
            return athlete.stripe_customer_id

        customer = stripe.Customer.create(
            email=athlete.user.email,
            name=athlete.user.get_full_name() or athlete.user.username,
            metadata={
                "user_id": str(athlete.user_id),
                "athlete_id": str(athlete.pk),
            },
        )
        from athletes.models import AthleteProfile
        AthleteProfile.objects.filter(pk=athlete.pk).update(
            stripe_customer_id=customer["id"]
        )
        athlete.stripe_customer_id = customer["id"]
        return customer["id"]

    @staticmethod
    def sync_email(athlete) -> None:
        if not athlete.stripe_customer_id:
            return
        stripe.Customer.modify(athlete.stripe_customer_id, email=athlete.user.email)

    @staticmethod
    def create_portal_session(athlete, return_url: str) -> str:
        """Return a Stripe Billing Portal URL for self-service card management."""
        customer_id = StripeCustomerService.get_or_create(athlete)
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session["url"]


# ---------------------------------------------------------------------------
# StripeCheckoutService  (destination charges — Connect Express)
# ---------------------------------------------------------------------------


class StripeCheckoutService:
    """
    Create Stripe Checkout Sessions using destination charges.

    Destination charges route the full payment through the platform account.
    Stripe automatically:
    - Keeps platform's application_fee_amount on the platform
    - Transfers the remainder to the academy's Express account

    This is the correct pattern for marketplace businesses where the platform
    is the merchant of record (vs. direct charges on the connected account).
    """

    @staticmethod
    def _require_connect_account(academy) -> str:
        """Return academy's Connect account ID or raise ValueError."""
        from payments.models import StripeAcademyConfig
        try:
            config = StripeAcademyConfig.objects.get(academy=academy)
        except StripeAcademyConfig.DoesNotExist:
            raise ValueError(
                f"Academy '{academy.name}' has not started Stripe onboarding."
            )
        if not config.stripe_connect_account_id:
            raise ValueError(
                f"Academy '{academy.name}' has not completed Stripe onboarding."
            )
        if not config.charges_enabled:
            raise ValueError(
                f"Academy '{academy.name}' is not yet verified to accept payments. "
                "Please complete the Stripe onboarding process."
            )
        return config.stripe_connect_account_id

    @staticmethod
    def create_subscription_checkout(
        athlete, plan, success_url: str, cancel_url: str
    ) -> str:
        """
        Checkout Session for MONTHLY / ANNUAL plans (mode='subscription').

        Uses subscription_data.application_fee_percent so the platform fee
        is charged on every recurring invoice automatically.
        Requires the plan to have a stripe_price_id set.
        """
        academy = plan.academy
        connect_account_id = StripeCheckoutService._require_connect_account(academy)

        if not plan.stripe_price_id:
            raise ValueError(
                f"Plan '{plan.name}' has no Stripe Price. "
                "Run the sync_stripe_plans management command first."
            )

        customer_id = StripeCustomerService.get_or_create(athlete)
        currency = _academy_currency(academy)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            subscription_data={
                "application_fee_percent": _platform_fee_percent(),
                "transfer_data": {"destination": connect_account_id},
                "metadata": {
                    "plan_id": str(plan.pk),
                    "academy_id": str(academy.pk),
                    "athlete_id": str(athlete.pk),
                    "purpose": "subscription",
                },
            },
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "plan_id": str(plan.pk),
                "academy_id": str(academy.pk),
                "athlete_id": str(athlete.pk),
                "purpose": "subscription",
            },
        )
        return session["url"]

    @staticmethod
    def create_one_time_checkout(
        athlete, plan, success_url: str, cancel_url: str
    ) -> str:
        """
        Checkout Session for CLASS_PASS / DROP_IN plans (mode='payment').

        Uses payment_intent_data.application_fee_amount for the destination charge.
        """
        academy = plan.academy
        connect_account_id = StripeCheckoutService._require_connect_account(academy)

        customer_id = StripeCustomerService.get_or_create(athlete)
        currency = _academy_currency(academy)
        amount_cents = int(plan.price * 100)
        fee_cents = _compute_fee_cents(amount_cents)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="payment",
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency": currency,
                    "unit_amount": amount_cents,
                    "product_data": {"name": plan.name},
                },
            }],
            payment_intent_data={
                "application_fee_amount": fee_cents,
                "transfer_data": {"destination": connect_account_id},
                "metadata": {
                    "plan_id": str(plan.pk),
                    "academy_id": str(academy.pk),
                    "athlete_id": str(athlete.pk),
                    "purpose": "one_time_plan",
                    "platform_fee_cents": str(fee_cents),
                },
            },
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "plan_id": str(plan.pk),
                "academy_id": str(academy.pk),
                "athlete_id": str(athlete.pk),
                "purpose": "one_time_plan",
                "platform_fee_cents": str(fee_cents),
            },
        )
        return session["url"]

    @staticmethod
    def create_seminar_checkout(
        athlete, seminar, registration, success_url: str, cancel_url: str
    ) -> str:
        """
        Checkout Session for a paid seminar registration.

        application_fee_amount is calculated and embedded in metadata so the
        payment_intent.succeeded webhook can build the Payment record.
        """
        academy = seminar.academy
        connect_account_id = StripeCheckoutService._require_connect_account(academy)

        customer_id = StripeCustomerService.get_or_create(athlete)
        currency = _academy_currency(academy)
        amount_cents = int(seminar.price * 100)
        fee_cents = _compute_fee_cents(amount_cents)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="payment",
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency": currency,
                    "unit_amount": amount_cents,
                    "product_data": {"name": seminar.title},
                },
            }],
            payment_intent_data={
                "application_fee_amount": fee_cents,
                "transfer_data": {"destination": connect_account_id},
                "metadata": {
                    "seminar_id": str(seminar.pk),
                    "seminar_registration_id": str(registration.pk),
                    "athlete_id": str(athlete.pk),
                    "academy_id": str(academy.pk),
                    "purpose": "seminar",
                    "platform_fee_cents": str(fee_cents),
                },
            },
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "seminar_id": str(seminar.pk),
                "seminar_registration_id": str(registration.pk),
                "athlete_id": str(athlete.pk),
                "academy_id": str(academy.pk),
                "purpose": "seminar",
                "platform_fee_cents": str(fee_cents),
            },
        )
        return session["url"]


# ---------------------------------------------------------------------------
# Refund helper
# ---------------------------------------------------------------------------


def refund_payment(payment) -> dict:
    """
    Issue a full refund for a Payment record and update its local status.

    Stripe automatically reverses the transfer to the academy's Express account
    when a refund is issued on a destination charge.
    """
    if payment.status != payment.Status.SUCCEEDED:
        raise ValueError(f"Cannot refund a payment with status '{payment.status}'.")

    refund = stripe.Refund.create(payment_intent=payment.stripe_payment_intent_id)

    from payments.models import Payment
    Payment.objects.filter(pk=payment.pk).update(status=Payment.Status.REFUNDED)
    return refund


# ---------------------------------------------------------------------------
# Webhook event dispatcher
# ---------------------------------------------------------------------------


def dispatch_webhook_event(event: dict) -> None:
    """Route a Stripe event to the correct handler."""
    handlers = {
        # Connect account lifecycle
        "account.updated": _handle_account_updated,
        # Checkout
        "checkout.session.completed": _handle_checkout_completed,
        # Invoice (subscriptions)
        "invoice.payment_succeeded": _handle_invoice_payment_succeeded,
        "invoice.payment_failed": _handle_invoice_payment_failed,
        # PaymentIntents (one-time)
        "payment_intent.succeeded": _handle_payment_intent_succeeded,
        "payment_intent.payment_failed": _handle_payment_intent_failed,
        # Subscription lifecycle
        "customer.subscription.deleted": _handle_subscription_deleted,
        "customer.subscription.updated": _handle_subscription_updated,
        # Refunds
        "charge.refunded": _handle_charge_refunded,
    }
    handler = handlers.get(event["type"])
    if handler:
        handler(event["data"]["object"])
    else:
        logger.debug("Unhandled Stripe event: %s", event["type"])


# ---------------------------------------------------------------------------
# Individual handlers (private)
# ---------------------------------------------------------------------------


def _handle_account_updated(stripe_account: dict) -> None:
    """Sync Express account verification status."""
    StripeConnectExpressService.sync_account_status(stripe_account)


def _handle_checkout_completed(session: dict) -> None:
    """
    checkout.session.completed fires as soon as Stripe accepts the payment.

    For subscriptions: store stripe_subscription_id so the following
    invoice.payment_succeeded can correlate the local Subscription.
    For one-time payments: the actual record creation happens in
    payment_intent.succeeded (the authoritative money-moved event).
    """
    metadata = session.get("metadata", {})
    purpose = metadata.get("purpose")

    if purpose == "subscription" and session.get("subscription"):
        from membership.models import Subscription
        stripe_sub_id = session["subscription"]
        existing = Subscription.objects.filter(
            stripe_subscription_id=stripe_sub_id
        ).exists()
        if not existing:
            stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)
            _sync_subscription_from_stripe(
                stripe_sub,
                plan_id=_int(metadata.get("plan_id")),
                athlete_id=_int(metadata.get("athlete_id")),
            )


def _handle_invoice_payment_succeeded(invoice: dict) -> None:
    """
    Subscription payment confirmed — ensure local Subscription is ACTIVE
    and create/update a Payment record.
    """
    from membership.models import Subscription
    from payments.models import Payment

    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return

    try:
        sub = Subscription.objects.select_related("plan__academy", "athlete").get(
            stripe_subscription_id=stripe_sub_id
        )
    except Subscription.DoesNotExist:
        logger.warning("invoice.payment_succeeded: no Subscription for %s", stripe_sub_id)
        return

    # Activate subscription
    if sub.status != Subscription.Status.ACTIVE:
        Subscription.objects.filter(pk=sub.pk).update(status=Subscription.Status.ACTIVE)

    # Build Payment record
    amount_paid = Decimal(str(invoice.get("amount_paid", 0))) / 100
    if amount_paid <= 0:
        return

    pi_id = invoice.get("payment_intent", "")
    fee_percent = _platform_fee_percent()
    fee = (amount_paid * Decimal(str(fee_percent)) / 100).quantize(Decimal("0.01"))
    currency = invoice.get("currency", "eur")
    invoice_url = invoice.get("hosted_invoice_url", "") or invoice.get("invoice_pdf", "")

    Payment.objects.get_or_create(
        stripe_payment_intent_id=pi_id,
        defaults={
            "athlete": sub.athlete,
            "academy": sub.plan.academy,
            "payment_type": Payment.PaymentType.SUBSCRIPTION,
            "amount_paid": amount_paid,
            "platform_fee": fee,
            "academy_net": amount_paid - fee,
            "currency": currency,
            "status": Payment.Status.SUCCEEDED,
            "stripe_invoice_id": invoice.get("id", ""),
            "stripe_invoice_url": invoice_url,
            "extra_metadata": {
                "stripe_subscription_id": stripe_sub_id,
                "plan_id": str(sub.plan_id),
            },
        },
    )


def _handle_invoice_payment_failed(invoice: dict) -> None:
    from membership.models import Subscription

    stripe_sub_id = invoice.get("subscription")
    if stripe_sub_id:
        Subscription.objects.filter(
            stripe_subscription_id=stripe_sub_id,
            status=Subscription.Status.ACTIVE,
        ).update(status=Subscription.Status.PAUSED)


def _handle_payment_intent_succeeded(pi: dict) -> None:
    """
    One-time payment confirmed — create a Payment record and update related models.

    The metadata embedded when creating the Checkout Session tells us the purpose
    and which local objects to update.
    """
    from membership.models import SeminarRegistration
    from payments.models import Payment

    metadata = pi.get("metadata", {})
    purpose = metadata.get("purpose")
    pi_id = pi["id"]
    amount_cents = pi.get("amount_received", pi.get("amount", 0))
    fee_cents = int(metadata.get("platform_fee_cents", "0") or "0")
    currency = pi.get("currency", "eur")

    amount_paid = Decimal(str(amount_cents)) / 100
    platform_fee = Decimal(str(fee_cents)) / 100
    academy_net = amount_paid - platform_fee

    athlete_id = _int(metadata.get("athlete_id"))
    academy_id = _int(metadata.get("academy_id"))

    if not athlete_id or not academy_id:
        return

    # Determine payment type
    type_map = {
        "seminar": Payment.PaymentType.SEMINAR,
        "one_time_plan": Payment.PaymentType.ONE_TIME_PLAN,
    }
    payment_type = type_map.get(purpose, Payment.PaymentType.ONE_TIME_PLAN)

    payment, created = Payment.objects.get_or_create(
        stripe_payment_intent_id=pi_id,
        defaults={
            "athlete_id": athlete_id,
            "academy_id": academy_id,
            "payment_type": payment_type,
            "amount_paid": amount_paid,
            "platform_fee": platform_fee,
            "academy_net": academy_net,
            "currency": currency,
            "status": Payment.Status.SUCCEEDED,
            "extra_metadata": dict(metadata),
        },
    )

    if not created:
        return  # Idempotent: already processed

    # Update related records
    if purpose == "seminar":
        reg_id = _int(metadata.get("seminar_registration_id"))
        if reg_id:
            SeminarRegistration.objects.filter(pk=reg_id).update(
                payment_status=SeminarRegistration.PaymentStatus.PAID,
                stripe_payment_intent_id=pi_id,
            )


def _handle_payment_intent_failed(pi: dict) -> None:
    logger.warning(
        "PaymentIntent %s failed: %s",
        pi.get("id"),
        pi.get("last_payment_error", {}).get("message", "unknown"),
    )


def _handle_subscription_deleted(stripe_sub: dict) -> None:
    from membership.models import Subscription

    Subscription.objects.filter(
        stripe_subscription_id=stripe_sub["id"]
    ).update(status=Subscription.Status.CANCELLED)


def _handle_subscription_updated(stripe_sub: dict) -> None:
    _sync_subscription_from_stripe(stripe_sub)


def _handle_charge_refunded(charge: dict) -> None:
    from membership.models import SeminarRegistration
    from payments.models import Payment

    pi_id = charge.get("payment_intent")
    if not pi_id:
        return

    Payment.objects.filter(
        stripe_payment_intent_id=pi_id,
        status=Payment.Status.SUCCEEDED,
    ).update(status=Payment.Status.REFUNDED)

    SeminarRegistration.objects.filter(
        stripe_payment_intent_id=pi_id,
        payment_status=SeminarRegistration.PaymentStatus.PAID,
    ).update(payment_status=SeminarRegistration.PaymentStatus.REFUNDED)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@transaction.atomic
def _sync_subscription_from_stripe(
    stripe_sub: dict, plan_id: int = None, athlete_id: int = None
):
    from membership.models import MembershipPlan, Subscription
    from athletes.models import AthleteProfile

    stripe_sub_id = stripe_sub["id"]
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
    local_status = status_map.get(stripe_sub.get("status", ""), Subscription.Status.PAUSED)

    existing = Subscription.objects.filter(stripe_subscription_id=stripe_sub_id).first()
    if existing:
        existing.status = local_status
        existing.save(update_fields=["status"])
        return existing

    if plan_id is None or athlete_id is None:
        return None

    try:
        plan = MembershipPlan.objects.get(pk=plan_id)
        athlete = AthleteProfile.objects.get(pk=athlete_id)
    except (MembershipPlan.DoesNotExist, AthleteProfile.DoesNotExist):
        logger.error("sync_subscription: plan %s or athlete %s not found", plan_id, athlete_id)
        return None

    from membership.services import SubscriptionService
    sub = SubscriptionService.subscribe(athlete=athlete, plan=plan)
    sub.stripe_subscription_id = stripe_sub_id
    sub.status = local_status
    sub.save(update_fields=["stripe_subscription_id", "status"])
    return sub
