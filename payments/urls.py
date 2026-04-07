from django.urls import path

from .views import (
    CheckoutSessionView,
    CustomerPortalView,
    PaymentMethodListView,
    SeminarCheckoutView,
    StripeWebhookView,
)

urlpatterns = [
    path("checkout/", CheckoutSessionView.as_view(), name="stripe-checkout"),
    path("portal/", CustomerPortalView.as_view(), name="stripe-portal"),
    path("seminar-checkout/", SeminarCheckoutView.as_view(), name="seminar-checkout"),
    path("payment-methods/", PaymentMethodListView.as_view(), name="payment-methods"),
    path("webhooks/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
