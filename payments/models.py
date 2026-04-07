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
    Per-academy Stripe configuration.

    Stores statement descriptor and currency preferences so each academy
    can display customised billing information to their athletes.
    """

    statement_descriptor = models.CharField(
        max_length=22,
        blank=True,
        help_text="Appears on athlete's card statement (max 22 chars).",
    )
    default_currency = models.CharField(max_length=3, default="usd")
    is_onboarded = models.BooleanField(default=False)

    class Meta:
        unique_together = [("academy",)]

    def __str__(self):
        return f"Stripe config – {self.academy}"
