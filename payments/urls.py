from django.urls import path

from .views import (
    AcademyConnectStatusView,
    AcademyOnboardingView,
    AcademyStripeDashboardView,
    CheckoutSessionView,
    CustomerPortalView,
    PaymentListView,
    PaymentMethodListView,
    SeminarCheckoutView,
    StripeWebhookView,
)

urlpatterns = [
    # ── Stripe Connect Express — academy onboarding ───────────────────────────
    path(
        "academy-onboarding/",
        AcademyOnboardingView.as_view(),
        name="academy-onboarding",
    ),
    path(
        "academy/<int:academy_id>/connect-status/",
        AcademyConnectStatusView.as_view(),
        name="academy-connect-status",
    ),
    path(
        "academy/<int:academy_id>/dashboard/",
        AcademyStripeDashboardView.as_view(),
        name="academy-stripe-dashboard",
    ),
    # ── Checkout sessions (athletes) ──────────────────────────────────────────
    path("checkout/", CheckoutSessionView.as_view(), name="stripe-checkout"),
    path(
        "seminar-checkout/",
        SeminarCheckoutView.as_view(),
        name="seminar-checkout",
    ),
    path("portal/", CustomerPortalView.as_view(), name="stripe-portal"),
    # ── Payment history (local DB reads — no Stripe calls) ────────────────────
    path("history/", PaymentListView.as_view(), name="payment-history"),
    # ── Saved cards ───────────────────────────────────────────────────────────
    path(
        "payment-methods/",
        PaymentMethodListView.as_view(),
        name="payment-methods",
    ),
    # ── Webhook receiver (no JWT auth — verified by Stripe signature) ─────────
    path(
        "webhooks/stripe/",
        StripeWebhookView.as_view(),
        name="stripe-webhook",
    ),
]
