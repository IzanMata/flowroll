from rest_framework import serializers

from membership.models import MembershipPlan, Seminar


class CheckoutSessionRequestSerializer(serializers.Serializer):
    plan_id = serializers.PrimaryKeyRelatedField(
        queryset=MembershipPlan.objects.filter(is_active=True),
        help_text="ID of the active MembershipPlan to subscribe to.",
    )
    success_url = serializers.URLField(
        help_text="URL Stripe redirects to after successful payment."
    )
    cancel_url = serializers.URLField(
        help_text="URL Stripe redirects to if the user cancels."
    )


class CustomerPortalRequestSerializer(serializers.Serializer):
    return_url = serializers.URLField(
        help_text="URL to return to after leaving the Stripe Customer Portal."
    )


class SeminarCheckoutRequestSerializer(serializers.Serializer):
    seminar_id = serializers.PrimaryKeyRelatedField(
        queryset=Seminar.objects.filter(status=Seminar.Status.OPEN),
        help_text="ID of the open Seminar to register and pay for.",
    )
    success_url = serializers.URLField()
    cancel_url = serializers.URLField()


class PaymentMethodSerializer(serializers.Serializer):
    id = serializers.CharField()
    brand = serializers.CharField()
    last4 = serializers.CharField()
    exp_month = serializers.IntegerField()
    exp_year = serializers.IntegerField()
    is_default = serializers.BooleanField()
