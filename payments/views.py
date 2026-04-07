"""
Payment API views for FlowRoll.

All Stripe interactions go through the service layer — views only validate
input, call services, and return responses.

Endpoints
---------
POST /api/v1/payments/checkout/          — Create a Checkout Session for a plan
POST /api/v1/payments/portal/            — Create a Billing Portal session
POST /api/v1/payments/seminar-checkout/  — Create a Checkout Session for a seminar
GET  /api/v1/payments/payment-methods/   — List saved card payment methods
POST /api/v1/payments/webhooks/stripe/   — Stripe webhook receiver (no auth)
"""

import logging

import stripe
from django.conf import settings
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from membership.services import SeminarService
from payments.models import StripeWebhookEvent
from payments.serializers import (
    CheckoutSessionRequestSerializer,
    CustomerPortalRequestSerializer,
    PaymentMethodSerializer,
    SeminarCheckoutRequestSerializer,
)
from payments.services import (
    StripeCustomerService,
    StripePaymentService,
    StripeSubscriptionService,
    dispatch_webhook_event,
)

logger = logging.getLogger(__name__)


class CheckoutSessionView(APIView):
    """
    Create a Stripe Checkout Session for a membership plan.

    Returns a `checkout_url` that the client should redirect the user to.
    Stripe handles card collection; on success the webhook activates the
    subscription and the client polls for the updated subscription status.

    POST /api/v1/payments/checkout/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutSessionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = serializer.validated_data["plan_id"]
        success_url = serializer.validated_data["success_url"]
        cancel_url = serializer.validated_data["cancel_url"]

        try:
            athlete = request.user.profile
        except Exception:
            return Response(
                {"detail": "No athlete profile found for this user."}, status=400
            )

        try:
            checkout_url = StripeSubscriptionService.create_checkout_session(
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


class CustomerPortalView(APIView):
    """
    Create a Stripe Billing Portal session.

    Returns a `portal_url` that the client should redirect the user to.
    Athletes can update their card, change plans, or cancel subscriptions
    through the portal. Any changes trigger webhook events that are synced
    back into FlowRoll's DB automatically.

    POST /api/v1/payments/portal/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CustomerPortalRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return_url = serializer.validated_data["return_url"]

        try:
            athlete = request.user.profile
        except Exception:
            return Response(
                {"detail": "No athlete profile found for this user."}, status=400
            )

        try:
            portal_url = StripeCustomerService.create_portal_session(
                athlete=athlete, return_url=return_url
            )
        except stripe.StripeError as exc:
            logger.error("Stripe error creating portal session: %s", exc)
            return Response({"detail": "Payment provider error. Please try again."}, status=502)

        return Response({"portal_url": portal_url}, status=200)


class SeminarCheckoutView(APIView):
    """
    Register an athlete for a seminar and create a Stripe Checkout Session.

    The registration is created first (may be CONFIRMED or WAITLISTED).
    If the seminar is free (price=0.00), no Stripe session is created and
    the registration is returned immediately.

    POST /api/v1/payments/seminar-checkout/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SeminarCheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        seminar = serializer.validated_data["seminar_id"]
        success_url = serializer.validated_data["success_url"]
        cancel_url = serializer.validated_data["cancel_url"]

        try:
            athlete = request.user.profile
        except Exception:
            return Response(
                {"detail": "No athlete profile found for this user."}, status=400
            )

        try:
            registration = SeminarService.register(athlete=athlete, seminar=seminar)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        # Free seminar — no payment needed
        if seminar.price == 0:
            return Response(
                {"registration_status": registration.status, "checkout_url": None},
                status=201,
            )

        try:
            checkout_url = StripePaymentService.create_seminar_checkout_session(
                athlete=athlete,
                seminar=seminar,
                registration=registration,
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except stripe.StripeError as exc:
            logger.error("Stripe error creating seminar checkout: %s", exc)
            return Response({"detail": "Payment provider error. Please try again."}, status=502)

        return Response(
            {
                "registration_status": registration.status,
                "checkout_url": checkout_url,
            },
            status=201,
        )


class PaymentMethodListView(APIView):
    """
    List saved card payment methods for the current user.

    Returns masked card details only — raw card data is never stored in FlowRoll.

    GET /api/v1/payments/payment-methods/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            athlete = request.user.profile
        except Exception:
            return Response(
                {"detail": "No athlete profile found for this user."}, status=400
            )

        if not athlete.stripe_customer_id:
            return Response({"results": []}, status=200)

        try:
            stripe_customer = stripe.Customer.retrieve(
                athlete.stripe_customer_id,
                expand=["invoice_settings.default_payment_method"],
            )
            payment_methods = stripe.PaymentMethod.list(
                customer=athlete.stripe_customer_id,
                type="card",
            )
        except stripe.StripeError as exc:
            logger.error("Stripe error listing payment methods: %s", exc)
            return Response({"detail": "Payment provider error. Please try again."}, status=502)

        default_pm_id = None
        default_pm = stripe_customer.get("invoice_settings", {}).get(
            "default_payment_method"
        )
        if default_pm:
            default_pm_id = (
                default_pm["id"] if isinstance(default_pm, dict) else default_pm
            )

        results = []
        for pm in payment_methods.get("data", []):
            card = pm.get("card", {})
            results.append(
                {
                    "id": pm["id"],
                    "brand": card.get("brand", ""),
                    "last4": card.get("last4", ""),
                    "exp_month": card.get("exp_month", 0),
                    "exp_year": card.get("exp_year", 0),
                    "is_default": pm["id"] == default_pm_id,
                }
            )

        serializer = PaymentMethodSerializer(results, many=True)
        return Response({"results": serializer.data}, status=200)


class StripeWebhookView(APIView):
    """
    Receive and process Stripe webhook events.

    Authentication is performed via Stripe's signature verification
    (STRIPE_WEBHOOK_SECRET), not JWT. This endpoint must be excluded from
    CSRF and registered in the Stripe dashboard.

    POST /api/v1/payments/webhooks/stripe/
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []  # Do not throttle — Stripe retries would be blocked

    def post(self, request):
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET

        if not webhook_secret:
            # In development without a webhook secret, skip signature check.
            # In production this env var must always be set.
            logger.warning("STRIPE_WEBHOOK_SECRET is not configured — skipping signature check.")
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
            except ValueError:
                return Response(status=400)
            except stripe.error.SignatureVerificationError:
                return Response(status=400)

        # Idempotency: skip already-processed events
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
            # Return 200 so Stripe does not keep retrying an application-level error
            return Response({"detail": "processing error logged"}, status=200)

        return Response(status=200)
