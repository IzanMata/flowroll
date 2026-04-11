from django.contrib import admin

from .models import Payment, StripeAcademyConfig, StripeWebhookEvent


@admin.register(StripeWebhookEvent)
class StripeWebhookEventAdmin(admin.ModelAdmin):
    list_display = ["stripe_event_id", "event_type", "processed", "created_at"]
    list_filter = ["event_type", "processed"]
    search_fields = ["stripe_event_id", "event_type"]
    readonly_fields = [
        "stripe_event_id", "event_type", "payload",
        "processed", "processing_error", "created_at",
    ]
    ordering = ["-created_at"]


@admin.register(StripeAcademyConfig)
class StripeAcademyConfigAdmin(admin.ModelAdmin):
    list_display = [
        "academy", "stripe_connect_account_id", "default_currency",
        "charges_enabled", "payouts_enabled", "onboarding_completed_at",
    ]
    list_filter = ["charges_enabled", "payouts_enabled", "default_currency"]
    search_fields = ["academy__name", "stripe_connect_account_id"]
    readonly_fields = ["onboarding_completed_at", "created_at", "updated_at"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "id", "athlete", "academy", "payment_type", "amount_paid",
        "platform_fee", "academy_net", "currency", "status", "created_at",
    ]
    list_filter = ["payment_type", "status", "currency"]
    search_fields = [
        "athlete__user__username", "academy__name",
        "stripe_payment_intent_id", "stripe_charge_id",
    ]
    readonly_fields = [
        "athlete", "academy", "payment_type", "amount_paid", "platform_fee",
        "academy_net", "currency", "status", "stripe_payment_intent_id",
        "stripe_charge_id", "stripe_invoice_id", "stripe_invoice_url",
        "extra_metadata", "created_at",
    ]
    ordering = ["-created_at"]
