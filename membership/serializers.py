from rest_framework import serializers

from academies.models import Academy

from .models import (DojoTabTransaction, MembershipPlan, Seminar,
                     SeminarRegistration, Subscription, StripeCustomer,
                     StripePaymentMethod, StripeSubscription, StripePayment,
                     StripeConnectedAccount, PlatformCommission, MarketplaceTransaction,
                     AcademyEarnings)


class MembershipPlanSerializer(serializers.ModelSerializer):
    """Serializes a MembershipPlan for list and detail operations."""

    class Meta:
        model = MembershipPlan
        fields = [
            "id",
            "academy",
            "name",
            "plan_type",
            "price",
            "class_limit",
            "duration_days",
            "is_active",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializes a Subscription for list and detail operations.

    plan_name is a read-only convenience field. Use SubscriptionService.subscribe()
    to create subscriptions — do not POST to the endpoint directly.
    """

    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "athlete",
            "plan",
            "plan_name",
            "start_date",
            "end_date",
            "status",
            "classes_remaining",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class PromotionReadinessSerializer(serializers.Serializer):
    """Read-only serializer for the PromotionReadiness dataclass."""

    is_ready = serializers.BooleanField()
    mat_hours_ok = serializers.BooleanField()
    months_at_belt_ok = serializers.BooleanField()
    stripes_ok = serializers.BooleanField()
    current_mat_hours = serializers.FloatField()
    required_mat_hours = serializers.FloatField()
    current_months = serializers.IntegerField()
    required_months = serializers.IntegerField()
    current_stripes = serializers.IntegerField()
    required_stripes = serializers.IntegerField()
    message = serializers.CharField()


class DojoTabTransactionSerializer(serializers.ModelSerializer):
    """
    Serializes a dojo tab transaction (DEBIT or CREDIT).

    billed and created_at are managed by DojoTabService and are read-only.
    Use DojoTabService.charge() or DojoTabService.credit() to create transactions.
    """

    class Meta:
        model = DojoTabTransaction
        fields = [
            "id",
            "athlete",
            "academy",
            "transaction_type",
            "amount",
            "description",
            "billed",
            "created_at",
        ]
        read_only_fields = ["billed", "created_at"]


class SeminarSerializer(serializers.ModelSerializer):
    """
    Serializes a Seminar for list and detail operations.

    spots_remaining is a model property (capacity − confirmed registrations)
    exposed as a read-only field. Use SeminarService.register() to book a spot.
    """

    spots_remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = Seminar
        fields = [
            "id",
            "academy",
            "title",
            "instructor_name",
            "description",
            "event_date",
            "capacity",
            "price",
            "status",
            "spots_remaining",
        ]


class EnrollmentSerializer(serializers.Serializer):
    """Input serializer for the enrollment endpoint."""

    academy = serializers.PrimaryKeyRelatedField(
        queryset=Academy.objects.filter(is_active=True),
        help_text="ID of the academy to join.",
    )
    plan = serializers.PrimaryKeyRelatedField(
        queryset=MembershipPlan.objects.filter(is_active=True),
        help_text="ID of the membership plan to subscribe to.",
    )


class SeminarRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializes a seminar registration record.

    status (CONFIRMED, WAITLISTED, CANCELLED) is managed by SeminarService
    and is read-only. Use SeminarService.register() and cancel_registration()
    to drive status transitions.
    """

    athlete_name = serializers.CharField(source="athlete.user.username", read_only=True)
    seminar_title = serializers.CharField(source="seminar.title", read_only=True)

    class Meta:
        model = SeminarRegistration
        fields = [
            "id",
            "seminar",
            "seminar_title",
            "athlete",
            "athlete_name",
            "status",
            "payment_status",
            "notes",
            "created_at",
        ]
        read_only_fields = ["status", "created_at"]


# ---------------------------------------------------------------------------
# Stripe Serializers
# ---------------------------------------------------------------------------


class StripePaymentMethodSerializer(serializers.ModelSerializer):
    """Serializes payment method details for display."""

    class Meta:
        model = StripePaymentMethod
        fields = [
            "id",
            "payment_method_type",
            "last_four",
            "brand",
            "exp_month",
            "exp_year",
            "is_default",
            "is_active",
            "created_at"
        ]
        read_only_fields = ["created_at"]


class StripeSubscriptionSerializer(serializers.ModelSerializer):
    """Serializes Stripe subscription details."""

    plan_name = serializers.CharField(source="subscription.plan.name", read_only=True)
    athlete_name = serializers.CharField(source="subscription.athlete.user.username", read_only=True)

    class Meta:
        model = StripeSubscription
        fields = [
            "id",
            "subscription",
            "plan_name",
            "athlete_name",
            "stripe_subscription_id",
            "status",
            "current_period_start",
            "current_period_end",
            "cancel_at_period_end",
            "canceled_at",
            "created_at"
        ]
        read_only_fields = ["created_at"]


class StripePaymentSerializer(serializers.ModelSerializer):
    """Serializes one-time payment details."""

    customer_name = serializers.CharField(source="stripe_customer.user.username", read_only=True)

    class Meta:
        model = StripePayment
        fields = [
            "id",
            "customer_name",
            "stripe_payment_intent_id",
            "payment_type",
            "amount",
            "currency",
            "status",
            "description",
            "created_at"
        ]
        read_only_fields = ["created_at"]


class AttachPaymentMethodSerializer(serializers.Serializer):
    """Input serializer for attaching a payment method."""

    payment_method_id = serializers.CharField(
        help_text="Stripe payment method ID from frontend"
    )
    set_as_default = serializers.BooleanField(
        default=False,
        help_text="Whether to set this as the default payment method"
    )


class StripeEnrollmentSerializer(serializers.Serializer):
    """Input serializer for enrollment with Stripe billing."""

    academy = serializers.PrimaryKeyRelatedField(
        queryset=Academy.objects.filter(is_active=True),
        help_text="ID of the academy to join."
    )
    plan = serializers.PrimaryKeyRelatedField(
        queryset=MembershipPlan.objects.filter(is_active=True),
        help_text="ID of the membership plan to subscribe to."
    )
    payment_method_id = serializers.CharField(
        required=False,
        help_text="Stripe payment method ID for recurring billing"
    )
    trial_days = serializers.IntegerField(
        default=0,
        min_value=0,
        max_value=365,
        help_text="Number of trial days (0-365)"
    )


class SeminarStripePaymentSerializer(serializers.Serializer):
    """Input serializer for seminar registration with Stripe payment."""

    seminar = serializers.PrimaryKeyRelatedField(
        queryset=Seminar.objects.filter(status=Seminar.Status.OPEN)
    )


class CreatePaymentIntentSerializer(serializers.Serializer):
    """Input serializer for creating a payment intent."""

    amount = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=0.50  # Stripe minimum
    )
    payment_type = serializers.ChoiceField(
        choices=StripePayment.PaymentType.choices
    )
    description = serializers.CharField(max_length=255)
    academy = serializers.PrimaryKeyRelatedField(
        queryset=Academy.objects.filter(is_active=True)
    )
    metadata = serializers.JSONField(required=False, default=dict)


# ---------------------------------------------------------------------------
# Stripe Connect (Marketplace) Serializers
# ---------------------------------------------------------------------------


class StripeConnectedAccountSerializer(serializers.ModelSerializer):
    """Serializes connected account details for academies."""

    academy_name = serializers.CharField(source="academy.name", read_only=True)
    is_fully_onboarded = serializers.BooleanField(read_only=True)

    class Meta:
        model = StripeConnectedAccount
        fields = [
            "id",
            "academy",
            "academy_name",
            "stripe_account_id",
            "account_type",
            "status",
            "details_submitted",
            "charges_enabled",
            "payouts_enabled",
            "business_name",
            "business_url",
            "support_email",
            "onboarding_url",
            "dashboard_url",
            "is_fully_onboarded",
            "created_at"
        ]
        read_only_fields = ["created_at"]


class PlatformCommissionSerializer(serializers.ModelSerializer):
    """Serializes platform commission configurations."""

    academy_name = serializers.CharField(source="academy.name", read_only=True)

    class Meta:
        model = PlatformCommission
        fields = [
            "id",
            "academy",
            "academy_name",
            "commission_type",
            "percentage_rate",
            "fixed_amount",
            "min_commission",
            "max_commission",
            "effective_from",
            "effective_until",
            "is_active",
            "created_at"
        ]
        read_only_fields = ["created_at"]


class MarketplaceTransactionSerializer(serializers.ModelSerializer):
    """Serializes marketplace transaction details."""

    customer_name = serializers.CharField(source="stripe_customer.user.username", read_only=True)
    academy_name = serializers.CharField(source="academy.name", read_only=True)
    academy_receives = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = MarketplaceTransaction
        fields = [
            "id",
            "stripe_payment_intent_id",
            "customer_name",
            "academy_name",
            "transaction_type",
            "status",
            "gross_amount",
            "platform_fee",
            "stripe_fee",
            "net_amount",
            "academy_receives",
            "currency",
            "customer_invoice_url",
            "platform_invoice_url",
            "created_at"
        ]
        read_only_fields = ["created_at", "academy_receives"]


class AcademyEarningsSerializer(serializers.ModelSerializer):
    """Serializes academy earnings analytics."""

    academy_name = serializers.CharField(source="academy.name", read_only=True)
    platform_fee_rate = serializers.DecimalField(max_digits=5, decimal_places=4, read_only=True)
    total_transactions = serializers.IntegerField(read_only=True)

    class Meta:
        model = AcademyEarnings
        fields = [
            "id",
            "academy",
            "academy_name",
            "year",
            "month",
            "total_gross",
            "total_platform_fees",
            "total_stripe_fees",
            "total_net",
            "platform_fee_rate",
            "subscription_count",
            "one_time_count",
            "seminar_count",
            "refund_count",
            "total_transactions",
            "currency"
        ]
        read_only_fields = ["platform_fee_rate", "total_transactions"]


class CreateConnectedAccountSerializer(serializers.Serializer):
    """Input serializer for creating connected accounts."""

    academy = serializers.PrimaryKeyRelatedField(
        queryset=Academy.objects.filter(is_active=True)
    )
    country = serializers.CharField(
        max_length=2,
        default="US",
        help_text="ISO 3166-1 alpha-2 country code"
    )


class CreateOnboardingLinkSerializer(serializers.Serializer):
    """Input serializer for creating onboarding links."""

    return_url = serializers.URLField(
        help_text="URL to redirect to after successful onboarding"
    )
    refresh_url = serializers.URLField(
        help_text="URL to redirect to if the link expires"
    )


class MarketplaceEnrollmentSerializer(serializers.Serializer):
    """Input serializer for marketplace enrollment."""

    academy = serializers.PrimaryKeyRelatedField(
        queryset=Academy.objects.filter(is_active=True)
    )
    plan = serializers.PrimaryKeyRelatedField(
        queryset=MembershipPlan.objects.filter(is_active=True)
    )
    payment_method_id = serializers.CharField(
        required=False,
        help_text="Stripe payment method ID (required for recurring plans)"
    )


class MarketplaceSeminarPaymentSerializer(serializers.Serializer):
    """Input serializer for marketplace seminar payments."""

    seminar = serializers.PrimaryKeyRelatedField(
        queryset=Seminar.objects.filter(status=Seminar.Status.OPEN)
    )


class EarningsSummarySerializer(serializers.Serializer):
    """Serializes earnings summary data."""

    total_gross = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_platform_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_stripe_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_net = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_transactions = serializers.IntegerField()
    platform_fee_rate = serializers.DecimalField(max_digits=5, decimal_places=4)
    year = serializers.IntegerField()
    month = serializers.IntegerField(required=False)
    subscription_count = serializers.IntegerField(required=False)
    seminar_count = serializers.IntegerField(required=False)
    one_time_count = serializers.IntegerField(required=False)
    monthly_breakdown = serializers.ListField(required=False)


class CommissionConfigurationSerializer(serializers.Serializer):
    """Input serializer for commission configuration."""

    academy = serializers.PrimaryKeyRelatedField(
        queryset=Academy.objects.filter(is_active=True),
        required=False,
        help_text="Academy (leave blank for platform default)"
    )
    commission_type = serializers.ChoiceField(
        choices=PlatformCommission.CommissionType.choices
    )
    percentage_rate = serializers.DecimalField(
        max_digits=5,
        decimal_places=4,
        required=False,
        help_text="Percentage rate (e.g., 0.1000 for 10%)"
    )
    fixed_amount = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        required=False,
        help_text="Fixed amount per transaction"
    )
    effective_from = serializers.DateField(
        required=False,
        help_text="When this configuration takes effect"
    )
