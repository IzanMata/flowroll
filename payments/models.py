from decimal import Decimal

from django.db import models

from core.mixins import TenantMixin, TimestampMixin


class StripeWebhookEvent(TimestampMixin):
    """
    Idempotency guard for Stripe webhook events.

    Stripe retries webhooks for up to 72 hours. Recording each event's ID
    prevents double-processing: the webhook view checks for existence before
    running the handler and marks the row processed=True on completion.
    """

    stripe_event_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["event_type", "processed"])]

    def __str__(self):
        status = "✓" if self.processed else "✗"
        return f"[{status}] {self.event_type} ({self.stripe_event_id})"


class StripeAcademyConfig(TenantMixin, TimestampMixin):
    """
    Stripe Connect Express configuration for each academy.

    Academies go through the Stripe Express onboarding flow before they can
    receive payouts. FlowRoll creates a destination charge on the platform
    account and Stripe automatically transfers the net amount to the academy's
    Express account, keeping ``platform_fee`` on the platform.
    """

    # Stripe Connect Express account ID (acct_...)
    stripe_connect_account_id = models.CharField(
        max_length=100, blank=True, db_index=True
    )
    statement_descriptor = models.CharField(
        max_length=22,
        blank=True,
        help_text="Appears on athlete's card statement (max 22 chars).",
    )
    default_currency = models.CharField(max_length=3, default="usd")
    # Express account verification status (synced from Stripe via webhooks)
    charges_enabled = models.BooleanField(default=False)
    payouts_enabled = models.BooleanField(default=False)
    details_submitted = models.BooleanField(default=False)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("academy",)]

    def __str__(self):
        if self.stripe_connect_account_id:
            status = "✓" if self.charges_enabled else "⏳"
            return f"[{status}] Stripe – {self.academy}"
        return f"[not connected] Stripe – {self.academy}"

    @property
    def is_ready(self) -> bool:
        """True when the academy can accept payments."""
        return bool(self.stripe_connect_account_id and self.charges_enabled)


class Payment(TenantMixin, TimestampMixin):
    """
    Immutable record of every successful Stripe payment on the platform.

    Written once by the webhook handler when payment_intent.succeeded fires.
    The frontend reads from this table — never queries Stripe in real time.

    Money flow for a 50 € payment at 10 % platform fee:
        amount_paid    = 50.00  (athlete paid)
        platform_fee   =  5.00  (FlowRoll keeps via application_fee_amount)
        stripe_fee     ≈  1.50  (estimated; exact value on the Stripe charge)
        academy_net    ≈ 43.50  (transferred to academy's Express account)
    """

    class PaymentType(models.TextChoices):
        SUBSCRIPTION = "SUBSCRIPTION", "Subscription"
        SEMINAR = "SEMINAR", "Seminar"
        ONE_TIME_PLAN = "ONE_TIME_PLAN", "One-time plan"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices)
    amount_paid = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Gross amount the athlete paid (e.g. 50.00).",
    )
    platform_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        help_text="FlowRoll's commission (application_fee_amount / 100).",
    )
    academy_net = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Amount transferred to the academy's Express account (before Stripe's own fees).",
    )
    currency = models.CharField(max_length=3, default="usd")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    # Stripe identifiers — used for refunds and audit trail, not for data reads
    stripe_payment_intent_id = models.CharField(
        max_length=100, unique=True, db_index=True
    )
    stripe_charge_id = models.CharField(max_length=100, blank=True, db_index=True)
    stripe_invoice_id = models.CharField(max_length=100, blank=True, db_index=True)
    # Optional link to the Stripe-hosted invoice PDF
    stripe_invoice_url = models.URLField(blank=True)
    # Extra context from Stripe metadata (plan_id, seminar_id, etc.)
    extra_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["athlete", "status"]),
            models.Index(fields=["academy", "status"]),
            models.Index(fields=["payment_type", "status"]),
        ]

    def __str__(self):
        return (
            f"{self.get_payment_type_display()} {self.amount_paid} {self.currency.upper()} "
            f"– {self.athlete} [{self.status}]"
        )
