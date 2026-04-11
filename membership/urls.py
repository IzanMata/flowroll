from django.urls import path

from .views import (
    CancelSubscriptionView, EnrollView, LeaveAcademyView,
    # Stripe views
    StripeEnrollView, AttachPaymentMethodView, PaymentMethodListView,
    DetachPaymentMethodView, StripeSubscriptionListView, CancelStripeSubscriptionView,
    SeminarStripePaymentView, CreatePaymentIntentView, stripe_webhook_view,
    # Stripe Connect (Marketplace) views
    CreateConnectedAccountView, CreateOnboardingLinkView, ConnectedAccountStatusView,
    CreateDashboardLinkView, MarketplaceEnrollView, MarketplaceSeminarPaymentView,
    AcademyEarningsView, MarketplaceTransactionListView, ConfigureCommissionView
)

urlpatterns = [
    # Original endpoints
    path("enroll/", EnrollView.as_view(), name="membership-enroll"),
    path("<int:academy_id>/leave/", LeaveAcademyView.as_view(), name="membership-leave"),
    path("subscriptions/<int:subscription_id>/cancel/", CancelSubscriptionView.as_view(), name="subscription-cancel"),

    # Stripe payment endpoints
    path("stripe-enroll/", StripeEnrollView.as_view(), name="stripe-enroll"),
    path("payment-methods/attach/", AttachPaymentMethodView.as_view(), name="attach-payment-method"),
    path("payment-methods/", PaymentMethodListView.as_view(), name="list-payment-methods"),
    path("payment-methods/<str:payment_method_id>/", DetachPaymentMethodView.as_view(), name="detach-payment-method"),
    path("stripe-subscriptions/", StripeSubscriptionListView.as_view(), name="list-stripe-subscriptions"),
    path("stripe-subscriptions/<int:subscription_id>/cancel/", CancelStripeSubscriptionView.as_view(), name="cancel-stripe-subscription"),
    path("seminars/stripe-register/", SeminarStripePaymentView.as_view(), name="seminar-stripe-register"),
    path("create-payment-intent/", CreatePaymentIntentView.as_view(), name="create-payment-intent"),

    # Stripe webhook endpoint
    path("stripe-webhook/", stripe_webhook_view, name="stripe-webhook"),

    # Stripe Connect (Marketplace) endpoints
    path("connect/create-account/", CreateConnectedAccountView.as_view(), name="create-connected-account"),
    path("connect/onboarding-link/", CreateOnboardingLinkView.as_view(), name="create-onboarding-link"),
    path("connect/status/", ConnectedAccountStatusView.as_view(), name="connected-account-status"),
    path("connect/dashboard-link/", CreateDashboardLinkView.as_view(), name="create-dashboard-link"),
    path("marketplace-enroll/", MarketplaceEnrollView.as_view(), name="marketplace-enroll"),
    path("marketplace-seminars/register/", MarketplaceSeminarPaymentView.as_view(), name="marketplace-seminar-register"),
    path("earnings/", AcademyEarningsView.as_view(), name="academy-earnings"),
    path("marketplace-transactions/", MarketplaceTransactionListView.as_view(), name="marketplace-transactions"),
    path("configure-commission/", ConfigureCommissionView.as_view(), name="configure-commission"),
]
