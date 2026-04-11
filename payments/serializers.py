from rest_framework import serializers

from academies.models import Academy
from membership.models import MembershipPlan, Seminar
from payments.models import Payment


class AcademyOnboardingRequestSerializer(serializers.Serializer):
    academy_id = serializers.PrimaryKeyRelatedField(
        queryset=Academy.objects.filter(is_active=True),
        help_text="ID of the academy to connect to Stripe.",
    )
    refresh_url = serializers.URLField(
        help_text="URL Stripe redirects to if the onboarding link expires."
    )
    return_url = serializers.URLField(
        help_text="URL Stripe redirects to after the owner completes onboarding."
    )


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


class PaymentSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for Payment records.

    Exposes Stripe invoice URL so the frontend can link directly to the
    Stripe-hosted PDF without FlowRoll generating any invoice documents.
    """

    athlete_username = serializers.CharField(
        source="athlete.user.username", read_only=True
    )
    payment_type_display = serializers.CharField(
        source="get_payment_type_display", read_only=True
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "payment_type",
            "payment_type_display",
            "amount_paid",
            "platform_fee",
            "academy_net",
            "currency",
            "status",
            "status_display",
            "athlete_username",
            "stripe_payment_intent_id",
            "stripe_invoice_url",
            "created_at",
        ]
        read_only_fields = fields
