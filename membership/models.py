from decimal import Decimal
from datetime import date

from django.db import models

from core.mixins import TenantMixin, TimestampMixin


class MembershipPlan(TenantMixin, TimestampMixin):
    """A membership plan offered by an academy (monthly, annual, class-pass, etc.)."""

    class PlanType(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        ANNUAL = "ANNUAL", "Annual"
        CLASS_PASS = "CLASS_PASS", "Class Pass"
        DROP_IN = "DROP_IN", "Drop-In"

    name = models.CharField(max_length=100)
    plan_type = models.CharField(max_length=20, choices=PlanType.choices)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    # Number of days the plan is valid. None means open-ended (e.g. monthly billing).
    duration_days = models.PositiveIntegerField(null=True, blank=True)
    # Max classes per plan period. None means unlimited.
    class_limit = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # Stripe integration
    stripe_product_id = models.CharField(max_length=100, blank=True)
    stripe_price_id = models.CharField(max_length=100, blank=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.academy})"


class Subscription(TimestampMixin):
    """An athlete's active (or historical) subscription to a MembershipPlan."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        CANCELLED = "CANCELLED", "Cancelled"
        PAUSED = "PAUSED", "Paused"

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(
        MembershipPlan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    classes_remaining = models.PositiveIntegerField(null=True, blank=True)
    # Stripe integration — null for CLASS_PASS/DROP_IN (one-time payments)
    stripe_subscription_id = models.CharField(
        max_length=100, blank=True, null=True, db_index=True
    )

    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["athlete", "status"]),
        ]

    def __str__(self):
        return f"{self.athlete} – {self.plan.name} ({self.status})"


class PromotionRequirement(models.Model):
    """
    Minimum criteria an athlete must meet before a belt promotion.

    academy is optional (null = global default). When both a global and an
    academy-specific requirement exist for the same belt, the academy-specific
    one wins (see PromotionService._get_requirement).
    """

    academy = models.ForeignKey(
        "academies.Academy",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="promotion_requirements",
    )
    belt = models.CharField(max_length=20)
    min_mat_hours = models.FloatField(default=0.0)
    min_months_at_belt = models.PositiveIntegerField(default=0)
    min_stripes_before_promotion = models.PositiveIntegerField(default=4)

    class Meta:
        unique_together = ("academy", "belt")

    def __str__(self):
        scope = str(self.academy) if self.academy_id else "global"
        return f"{self.belt} requirements ({scope})"


class DojoTabTransaction(TenantMixin, TimestampMixin):
    """A single debit or credit entry on an athlete's dojo tab."""

    class TransactionType(models.TextChoices):
        DEBIT = "DEBIT", "Debit"
        CREDIT = "CREDIT", "Credit"

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="tab_transactions",
    )
    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    billed = models.BooleanField(default=False)
    # Stripe integration — links this transaction to a Stripe PaymentIntent
    stripe_payment_intent_id = models.CharField(max_length=100, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.transaction_type} {self.amount} – {self.athlete}"


class DojoTabBalance(TenantMixin):
    """Running balance on an athlete's dojo tab per academy."""

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="tab_balances",
    )
    balance = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        unique_together = ("athlete", "academy")

    def __str__(self):
        return f"{self.athlete} balance: {self.balance}"


class Seminar(TenantMixin, TimestampMixin):
    """A special event or seminar hosted by an academy."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        FULL = "FULL", "Full"
        CANCELLED = "CANCELLED", "Cancelled"
        COMPLETED = "COMPLETED", "Completed"

    title = models.CharField(max_length=200)
    instructor_name = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    event_date = models.DateField()
    capacity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )

    class Meta:
        ordering = ["event_date"]

    @property
    def spots_remaining(self) -> int:
        confirmed = self.registrations.filter(
            status=SeminarRegistration.RegistrationStatus.CONFIRMED
        ).count()
        return max(0, self.capacity - confirmed)

    def __str__(self):
        return f"{self.title} ({self.event_date})"


class SeminarRegistration(TimestampMixin):
    """An athlete's registration for a seminar."""

    class RegistrationStatus(models.TextChoices):
        CONFIRMED = "CONFIRMED", "Confirmed"
        WAITLISTED = "WAITLISTED", "Waitlisted"
        CANCELLED = "CANCELLED", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        REFUNDED = "REFUNDED", "Refunded"

    seminar = models.ForeignKey(
        Seminar, on_delete=models.CASCADE, related_name="registrations"
    )
    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="seminar_registrations",
    )
    status = models.CharField(
        max_length=20,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.CONFIRMED,
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    notes = models.TextField(blank=True)
    # Stripe integration — links to the PaymentIntent used to pay for this registration
    stripe_payment_intent_id = models.CharField(max_length=100, blank=True, db_index=True)

    class Meta:
        unique_together = ("seminar", "athlete")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.athlete} – {self.seminar.title} ({self.status})"


# ---------------------------------------------------------------------------
# Stripe Integration Models
# ---------------------------------------------------------------------------


class StripeCustomer(TimestampMixin):
    """
    Links a Django User to a Stripe Customer ID.
    One-to-one relationship to allow multiple payment methods per user.
    """

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="stripe_customer"
    )
    stripe_customer_id = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_customer_id"]),
        ]

    def __str__(self):
        return f"{self.user} -> {self.stripe_customer_id}"


class StripePaymentMethod(TimestampMixin):
    """
    Stores Stripe payment method details for a customer.
    """

    class PaymentMethodType(models.TextChoices):
        CARD = "CARD", "Card"
        ACH_DEBIT = "ACH_DEBIT", "ACH Debit"
        SEPA_DEBIT = "SEPA_DEBIT", "SEPA Debit"

    stripe_customer = models.ForeignKey(
        StripeCustomer,
        on_delete=models.CASCADE,
        related_name="payment_methods"
    )
    stripe_payment_method_id = models.CharField(max_length=255, unique=True)
    payment_method_type = models.CharField(
        max_length=20,
        choices=PaymentMethodType.choices,
        default=PaymentMethodType.CARD
    )
    # Store last 4 digits and brand for display
    last_four = models.CharField(max_length=4, blank=True)
    brand = models.CharField(max_length=20, blank=True)  # visa, mastercard, etc.
    exp_month = models.PositiveSmallIntegerField(null=True, blank=True)
    exp_year = models.PositiveSmallIntegerField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_payment_method_id"]),
            models.Index(fields=["stripe_customer", "is_default"]),
        ]

    def __str__(self):
        return f"{self.brand} ending in {self.last_four}"


class StripeSubscription(TenantMixin, TimestampMixin):
    """
    Links internal Subscription to Stripe subscription for recurring billing.
    """

    class Status(models.TextChoices):
        INCOMPLETE = "INCOMPLETE", "Incomplete"
        INCOMPLETE_EXPIRED = "INCOMPLETE_EXPIRED", "Incomplete Expired"
        TRIALING = "TRIALING", "Trialing"
        ACTIVE = "ACTIVE", "Active"
        PAST_DUE = "PAST_DUE", "Past Due"
        CANCELED = "CANCELED", "Canceled"
        UNPAID = "UNPAID", "Unpaid"
        PAUSED = "PAUSED", "Paused"

    # Link to our internal subscription
    subscription = models.OneToOneField(
        Subscription,
        on_delete=models.CASCADE,
        related_name="stripe_subscription"
    )
    stripe_subscription_id = models.CharField(max_length=255, unique=True)
    stripe_customer = models.ForeignKey(
        StripeCustomer,
        on_delete=models.CASCADE,
        related_name="subscriptions"
    )
    status = models.CharField(max_length=20, choices=Status.choices)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_subscription_id"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Stripe subscription {self.stripe_subscription_id} -> {self.subscription}"


class StripePayment(TenantMixin, TimestampMixin):
    """
    Records one-time payments (seminars, dojo tab credits, etc.) processed via Stripe.
    """

    class PaymentType(models.TextChoices):
        SEMINAR = "SEMINAR", "Seminar Registration"
        DOJO_TAB_CREDIT = "DOJO_TAB_CREDIT", "Dojo Tab Credit"
        ONE_TIME_CLASS = "ONE_TIME_CLASS", "One-time Class"
        MERCHANDISE = "MERCHANDISE", "Merchandise"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PROCESSING = "PROCESSING", "Processing"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        CANCELED = "CANCELED", "Canceled"
        REFUNDED = "REFUNDED", "Refunded"
        PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "Partially Refunded"

    stripe_customer = models.ForeignKey(
        StripeCustomer,
        on_delete=models.CASCADE,
        related_name="payments"
    )
    stripe_payment_intent_id = models.CharField(max_length=255, unique=True)
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices)
    description = models.CharField(max_length=255, blank=True)

    # Optional foreign keys depending on payment type
    seminar_registration = models.ForeignKey(
        SeminarRegistration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stripe_payments"
    )

    # Metadata from Stripe webhook
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_payment_intent_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["payment_type"]),
        ]

    def __str__(self):
        return f"{self.payment_type} payment of {self.amount} {self.currency} ({self.status})"


class StripeWebhookEvent(TimestampMixin):
    """
    Idempotent processing of Stripe webhook events.
    Prevents duplicate processing of the same event.
    """

    stripe_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100)  # invoice.payment_succeeded, etc.
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_event_id"]),
            models.Index(fields=["event_type", "processed"]),
        ]

    def __str__(self):
        status = "✓" if self.processed else "⏳"
        return f"{status} {self.event_type} ({self.stripe_event_id})"


# ---------------------------------------------------------------------------
# Stripe Connect (Marketplace) Models
# ---------------------------------------------------------------------------


class StripeConnectedAccount(TenantMixin, TimestampMixin):
    """
    Links an Academy to a Stripe Connected Account for marketplace functionality.
    Enables direct payments to academies with platform commission.
    """

    class AccountType(models.TextChoices):
        EXPRESS = "EXPRESS", "Express"
        STANDARD = "STANDARD", "Standard"
        CUSTOM = "CUSTOM", "Custom"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Setup"
        RESTRICTED = "RESTRICTED", "Restricted"
        ENABLED = "ENABLED", "Enabled"
        REJECTED = "REJECTED", "Rejected"

    stripe_account_id = models.CharField(max_length=255, unique=True)
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.EXPRESS
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Onboarding status
    details_submitted = models.BooleanField(default=False)
    charges_enabled = models.BooleanField(default=False)
    payouts_enabled = models.BooleanField(default=False)

    # Business details
    business_name = models.CharField(max_length=255, blank=True)
    business_url = models.URLField(blank=True)
    support_email = models.EmailField(blank=True)

    # Onboarding URLs
    onboarding_url = models.URLField(blank=True)
    dashboard_url = models.URLField(blank=True)

    # Metadata from Stripe
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_account_id"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.academy.name} -> {self.stripe_account_id} ({self.status})"

    @property
    def is_fully_onboarded(self) -> bool:
        """Check if the account is fully set up and ready for payments."""
        return (
            self.status == self.Status.ENABLED
            and self.details_submitted
            and self.charges_enabled
            and self.payouts_enabled
        )


class PlatformCommission(TimestampMixin):
    """
    Configurable commission rates for academies.
    Allows different commission structures per academy or global defaults.
    """

    class CommissionType(models.TextChoices):
        PERCENTAGE = "PERCENTAGE", "Percentage"
        FIXED_AMOUNT = "FIXED_AMOUNT", "Fixed Amount"
        HYBRID = "HYBRID", "Hybrid (Fixed + Percentage)"

    # Optional academy (null = global default)
    academy = models.ForeignKey(
        "academies.Academy",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="platform_commissions",
    )

    commission_type = models.CharField(
        max_length=20,
        choices=CommissionType.choices,
        default=CommissionType.PERCENTAGE
    )

    # Percentage commission (e.g., 0.10 for 10%)
    percentage_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.1000"),
        help_text="Percentage rate (0.1000 = 10%)"
    )

    # Fixed amount commission
    fixed_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Fixed amount per transaction"
    )

    # Minimum commission
    min_commission = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Minimum commission per transaction"
    )

    # Maximum commission
    max_commission = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum commission per transaction (null = no limit)"
    )

    # Effective dates
    effective_from = models.DateField(default=date.today)
    effective_until = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["academy", "effective_from"]),
            models.Index(fields=["is_active"]),
        ]
        ordering = ["-effective_from"]

    def __str__(self):
        if self.commission_type == self.CommissionType.PERCENTAGE:
            rate = f"{self.percentage_rate * 100:.1f}%"
        elif self.commission_type == self.CommissionType.FIXED_AMOUNT:
            rate = f"${self.fixed_amount}"
        else:
            rate = f"{self.percentage_rate * 100:.1f}% + ${self.fixed_amount}"

        return f"{self.academy.name}: {rate} commission"

    def calculate_commission(self, amount: Decimal) -> Decimal:
        """Calculate commission for a given amount."""
        if self.commission_type == self.CommissionType.PERCENTAGE:
            commission = amount * self.percentage_rate
        elif self.commission_type == self.CommissionType.FIXED_AMOUNT:
            commission = self.fixed_amount
        else:  # HYBRID
            commission = (amount * self.percentage_rate) + self.fixed_amount

        # Apply min/max limits
        commission = max(commission, self.min_commission)
        if self.max_commission:
            commission = min(commission, self.max_commission)

        return commission


class MarketplaceTransaction(TenantMixin, TimestampMixin):
    """
    Records marketplace transactions with platform commissions and transfers.
    Links to both customer payments and connected account transfers.
    """

    class TransactionType(models.TextChoices):
        SUBSCRIPTION = "SUBSCRIPTION", "Subscription Payment"
        ONE_TIME = "ONE_TIME", "One-time Payment"
        SEMINAR = "SEMINAR", "Seminar Registration"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"
        PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "Partially Refunded"

    # Link to customer payment
    stripe_payment_intent_id = models.CharField(max_length=255, unique=True)
    stripe_customer = models.ForeignKey(
        StripeCustomer,
        on_delete=models.CASCADE,
        related_name="marketplace_transactions"
    )

    # Connected account details
    connected_account = models.ForeignKey(
        StripeConnectedAccount,
        on_delete=models.CASCADE,
        related_name="transactions"
    )

    # Transaction details
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Amounts (all in cents to match Stripe)
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2)  # Total paid by customer
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2)  # Our commission
    stripe_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))  # Stripe's fee
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)  # Amount to academy

    currency = models.CharField(max_length=3, default="USD")

    # Stripe IDs for tracking
    stripe_transfer_id = models.CharField(max_length=255, blank=True)  # Transfer to connected account
    stripe_application_fee_id = models.CharField(max_length=255, blank=True)  # Platform fee

    # Related objects
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_transactions"
    )
    seminar_registration = models.ForeignKey(
        SeminarRegistration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_transactions"
    )

    # Customer and invoice URLs from Stripe
    customer_invoice_url = models.URLField(blank=True)  # Customer's invoice
    platform_invoice_url = models.URLField(blank=True)  # Platform fee invoice

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_payment_intent_id"]),
            models.Index(fields=["connected_account", "status"]),
            models.Index(fields=["transaction_type", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.transaction_type} - {self.gross_amount} {self.currency} ({self.status})"

    @property
    def academy_receives(self) -> Decimal:
        """Amount the academy actually receives after all fees."""
        return self.gross_amount - self.platform_fee - self.stripe_fee


class AcademyEarnings(TenantMixin, TimestampMixin):
    """
    Analytics and summary data for academy earnings.
    Updated via signals when marketplace transactions are processed.
    """

    # Period tracking
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()  # 1-12

    # Connected account
    connected_account = models.ForeignKey(
        StripeConnectedAccount,
        on_delete=models.CASCADE,
        related_name="earnings"
    )

    # Earnings summary
    total_gross = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_platform_fees = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_stripe_fees = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_net = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    # Transaction counts
    subscription_count = models.PositiveIntegerField(default=0)
    one_time_count = models.PositiveIntegerField(default=0)
    seminar_count = models.PositiveIntegerField(default=0)
    refund_count = models.PositiveIntegerField(default=0)

    # Currency
    currency = models.CharField(max_length=3, default="USD")

    class Meta:
        unique_together = ("connected_account", "year", "month")
        indexes = [
            models.Index(fields=["academy", "year", "month"]),
            models.Index(fields=["connected_account", "year", "month"]),
        ]
        ordering = ["-year", "-month"]

    def __str__(self):
        return f"{self.academy.name} - {self.year}-{self.month:02d}: ${self.total_net}"

    @property
    def platform_fee_rate(self) -> Decimal:
        """Calculate effective platform fee rate for this period."""
        if self.total_gross > 0:
            return self.total_platform_fees / self.total_gross
        return Decimal("0.00")

    @property
    def total_transactions(self) -> int:
        """Total number of transactions in this period."""
        return self.subscription_count + self.one_time_count + self.seminar_count
