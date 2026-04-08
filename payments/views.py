"""
Payment API views — Stripe Connect Express marketplace model.

Money flows through the platform (destination charges):
  athlete pays → platform collects → Stripe keeps fees
  → platform keeps application_fee → academy's Express account gets the rest

Views never call Stripe in real time for data reads — only for action calls
(creating Checkout sessions, onboarding links). All payment history is read
from the local Payment model.
"""

import logging

import stripe
from django.db.models import Q
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from academies.models import Academy
from core.models import AcademyMembership
from membership.services import SeminarService
from payments.models import Payment, StripeAcademyConfig, StripeWebhookEvent
from payments.serializers import (
    AcademyOnboardingRequestSerializer,
    CheckoutSessionRequestSerializer,
    CustomerPortalRequestSerializer,
    PaymentMethodSerializer,
    PaymentSerializer,
    SeminarCheckoutRequestSerializer,
)
from payments.services import (
    StripeCheckoutService,
    StripeConnectExpressService,
    StripeCustomerService,
    dispatch_webhook_event,
    refund_payment,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_athlete(user):
    """Return the user's AthleteProfile or None."""
    try:
        return user.profile
    except Exception:
        return None


def _is_academy_owner_or_professor(user, academy):
    """True if the user is an active OWNER or PROFESSOR at the academy."""
    return AcademyMembership.objects.filter(
        user=user,
        academy=academy,
        is_active=True,
        role__in=[AcademyMembership.Role.OWNER, AcademyMembership.Role.PROFESSOR],
    ).exists()


def _is_academy_owner(user, academy):
    return AcademyMembership.objects.filter(
        user=user,
        academy=academy,
        is_active=True,
        role=AcademyMembership.Role.OWNER,
    ).exists()


# ---------------------------------------------------------------------------
# Connect Express — academy onboarding
# ---------------------------------------------------------------------------


class AcademyOnboardingView(APIView):
    """
    Initiate or resume Stripe Connect Express onboarding for an academy.

    The academy owner calls this endpoint to get a Stripe onboarding URL.
    After the owner completes KYC on Stripe, the account.updated webhook
    sets charges_enabled=True and the academy can start accepting payments.

    POST /api/v1/payments/academy-onboarding/
    Body: { "academy_id": 1, "refresh_url": "...", "return_url": "..." }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AcademyOnboardingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        academy = serializer.validated_data["academy_id"]
        refresh_url = serializer.validated_data["refresh_url"]
        return_url = serializer.validated_data["return_url"]

        if not _is_academy_owner(request.user, academy):
            return Response(
                {"detail": "Only academy owners can configure Stripe payments."},
                status=403,
            )

        try:
            onboarding_url = StripeConnectExpressService.create_account_and_onboarding_link(
                academy=academy,
                refresh_url=refresh_url,
                return_url=return_url,
            )
        except stripe.StripeError as exc:
            logger.error("Stripe error during onboarding for academy %s: %s", academy.pk, exc)
            return Response(
                {"detail": "Could not create Stripe onboarding link. Try again."},
                status=502,
            )

        return Response({"onboarding_url": onboarding_url}, status=200)


class AcademyConnectStatusView(APIView):
    """
    Return the Stripe Connect Express status for an academy.

    Professors and owners can check whether their academy is ready to accept
    payments (charges_enabled) and receive payouts (payouts_enabled).

    GET /api/v1/payments/academy/<academy_id>/connect-status/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, academy_id):
        try:
            academy = Academy.objects.get(pk=academy_id)
        except Academy.DoesNotExist:
            return Response({"detail": "Academy not found."}, status=404)

        if not _is_academy_owner_or_professor(request.user, academy):
            return Response({"detail": "Permission denied."}, status=403)

        return Response(
            StripeConnectExpressService.get_account_status(academy), status=200
        )


class AcademyStripeDashboardView(APIView):
    """
    Return a Stripe Express Dashboard login URL for the academy owner.

    Owners use this to see their payouts, transfer history, and issued
    invoices directly in Stripe's hosted dashboard.

    POST /api/v1/payments/academy/<academy_id>/dashboard/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, academy_id):
        try:
            academy = Academy.objects.get(pk=academy_id)
        except Academy.DoesNotExist:
            return Response({"detail": "Academy not found."}, status=404)

        if not _is_academy_owner(request.user, academy):
            return Response({"detail": "Only academy owners can access the Stripe dashboard."}, status=403)

        try:
            dashboard_url = StripeConnectExpressService.create_login_link(academy)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except stripe.StripeError as exc:
            logger.error("Stripe error creating dashboard link for academy %s: %s", academy_id, exc)
            return Response({"detail": "Could not create dashboard link."}, status=502)

        return Response({"dashboard_url": dashboard_url}, status=200)


# ---------------------------------------------------------------------------
# Checkout sessions
# ---------------------------------------------------------------------------


class CheckoutSessionView(APIView):
    """
    Create a Stripe Checkout Session for a membership plan.

    MONTHLY / ANNUAL → mode=subscription with application_fee_percent.
    CLASS_PASS / DROP_IN → mode=payment with application_fee_amount.

    Returns { "checkout_url": "https://checkout.stripe.com/..." }.

    POST /api/v1/payments/checkout/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutSessionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = serializer.validated_data["plan_id"]
        success_url = serializer.validated_data["success_url"]
        cancel_url = serializer.validated_data["cancel_url"]

        athlete = _get_athlete(request.user)
        if not athlete:
            return Response({"detail": "No athlete profile found."}, status=400)

        try:
            if plan.plan_type in ("MONTHLY", "ANNUAL"):
                checkout_url = StripeCheckoutService.create_subscription_checkout(
                    athlete=athlete,
                    plan=plan,
                    success_url=success_url,
                    cancel_url=cancel_url,
                )
            else:
                checkout_url = StripeCheckoutService.create_one_time_checkout(
                    athlete=athlete,
                    plan=plan,
                    success_url=success_url,
                    cancel_url=cancel_url,
                )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except stripe.StripeError as exc:
            logger.error("Stripe error creating checkout session: %s", exc)
            return Response({"detail": "Payment provider error. Please try again."}, status=502)

        return Response({"checkout_url": checkout_url}, status=200)


class SeminarCheckoutView(APIView):
    """
    Register an athlete for a seminar and create a Stripe Checkout Session.

    Free seminars (price=0) skip Stripe and confirm registration immediately.

    POST /api/v1/payments/seminar-checkout/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SeminarCheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        seminar = serializer.validated_data["seminar_id"]
        success_url = serializer.validated_data["success_url"]
        cancel_url = serializer.validated_data["cancel_url"]

        athlete = _get_athlete(request.user)
        if not athlete:
            return Response({"detail": "No athlete profile found."}, status=400)

        try:
            registration = SeminarService.register(athlete=athlete, seminar=seminar)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        if seminar.price == 0:
            return Response(
                {"registration_status": registration.status, "checkout_url": None},
                status=201,
            )

        try:
            checkout_url = StripeCheckoutService.create_seminar_checkout(
                athlete=athlete,
                seminar=seminar,
                registration=registration,
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except stripe.StripeError as exc:
            logger.error("Stripe error creating seminar checkout: %s", exc)
            return Response({"detail": "Payment provider error. Please try again."}, status=502)

        return Response(
            {"registration_status": registration.status, "checkout_url": checkout_url},
            status=201,
        )


class CustomerPortalView(APIView):
    """
    Create a Stripe Billing Portal session for card/subscription self-management.

    POST /api/v1/payments/portal/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CustomerPortalRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        athlete = _get_athlete(request.user)
        if not athlete:
            return Response({"detail": "No athlete profile found."}, status=400)

        try:
            portal_url = StripeCustomerService.create_portal_session(
                athlete=athlete,
                return_url=serializer.validated_data["return_url"],
            )
        except stripe.StripeError as exc:
            logger.error("Stripe portal error: %s", exc)
            return Response({"detail": "Payment provider error. Please try again."}, status=502)

        return Response({"portal_url": portal_url}, status=200)


# ---------------------------------------------------------------------------
# Payment history (reads from local DB — no Stripe calls)
# ---------------------------------------------------------------------------


class PaymentListView(APIView):
    """
    List Payment records for the current user.

    Athletes see their own payments.
    Professors / owners see all payments for their academy
    when ?academy=<id> is provided.

    GET /api/v1/payments/history/
    GET /api/v1/payments/history/?academy=<id>        (professor/owner only)
    GET /api/v1/payments/history/?payment_type=SEMINAR
    GET /api/v1/payments/history/?status=SUCCEEDED
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        academy_id = request.query_params.get("academy")
        payment_type = request.query_params.get("payment_type")
        status = request.query_params.get("status")

        if academy_id:
            try:
                academy = Academy.objects.get(pk=academy_id)
            except Academy.DoesNotExist:
                return Response({"detail": "Academy not found."}, status=404)

            if not _is_academy_owner_or_professor(request.user, academy):
                return Response({"detail": "Permission denied."}, status=403)

            qs = Payment.objects.filter(academy=academy).select_related("athlete__user")
        else:
            athlete = _get_athlete(request.user)
            if not athlete:
                return Response({"results": []}, status=200)
            qs = Payment.objects.filter(athlete=athlete).select_related("athlete__user")

        if payment_type:
            qs = qs.filter(payment_type=payment_type)
        if status:
            qs = qs.filter(status=status)

        serializer = PaymentSerializer(qs[:100], many=True)
        return Response({"results": serializer.data}, status=200)


class PaymentMethodListView(APIView):
    """
    List saved card payment methods for the current user (masked — no raw card data).

    GET /api/v1/payments/payment-methods/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        athlete = _get_athlete(request.user)
        if not athlete or not athlete.stripe_customer_id:
            return Response({"results": []}, status=200)

        try:
            stripe_customer = stripe.Customer.retrieve(
                athlete.stripe_customer_id,
                expand=["invoice_settings.default_payment_method"],
            )
            payment_methods = stripe.PaymentMethod.list(
                customer=athlete.stripe_customer_id, type="card"
            )
        except stripe.StripeError as exc:
            logger.error("Stripe error listing payment methods: %s", exc)
            return Response({"detail": "Payment provider error."}, status=502)

        default_pm = stripe_customer.get("invoice_settings", {}).get(
            "default_payment_method"
        )
        default_pm_id = (
            default_pm["id"] if isinstance(default_pm, dict) else default_pm
        ) if default_pm else None

        results = [
            {
                "id": pm["id"],
                "brand": pm.get("card", {}).get("brand", ""),
                "last4": pm.get("card", {}).get("last4", ""),
                "exp_month": pm.get("card", {}).get("exp_month", 0),
                "exp_year": pm.get("card", {}).get("exp_year", 0),
                "is_default": pm["id"] == default_pm_id,
            }
            for pm in payment_methods.get("data", [])
        ]
        return Response({"results": PaymentMethodSerializer(results, many=True).data}, status=200)


# ---------------------------------------------------------------------------
# Webhook receiver
# ---------------------------------------------------------------------------


class StripeWebhookView(APIView):
    """
    Receive and process Stripe webhook events.

    Verified via STRIPE_WEBHOOK_SECRET signature — no JWT auth.
    Returns 200 for all processed events (including errors) so Stripe
    does not retry application-level failures indefinitely.

    POST /api/v1/payments/webhooks/stripe/
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def post(self, request):
        from django.conf import settings

        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET

        if not webhook_secret:
            logger.warning("STRIPE_WEBHOOK_SECRET not set — skipping signature check.")
            try:
                import json
                event = json.loads(request.body)
            except Exception:
                return Response(status=400)
        else:
            try:
                event = stripe.Webhook.construct_event(
                    request.body, sig_header, webhook_secret
                )
            except (ValueError, stripe.error.SignatureVerificationError):
                return Response(status=400)

        webhook_event, created = StripeWebhookEvent.objects.get_or_create(
            stripe_event_id=event["id"],
            defaults={
                "event_type": event["type"],
                "payload": dict(event),
                "processed": False,
            },
        )

        if not created and webhook_event.processed:
            return Response({"detail": "already processed"}, status=200)

        try:
            dispatch_webhook_event(event)
            StripeWebhookEvent.objects.filter(stripe_event_id=event["id"]).update(
                processed=True
            )
        except Exception as exc:
            logger.exception("Error processing Stripe event %s", event.get("id"))
            StripeWebhookEvent.objects.filter(stripe_event_id=event["id"]).update(
                processing_error=str(exc)
            )
            return Response({"detail": "processing error logged"}, status=200)

        return Response(status=200)
