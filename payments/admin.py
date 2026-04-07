from django.contrib import admin

from .models import StripeAcademyConfig, StripeWebhookEvent


@admin.register(StripeWebhookEvent)
class StripeWebhookEventAdmin(admin.ModelAdmin):
    list_display = ["stripe_event_id", "event_type", "processed", "created_at"]
    list_filter = ["event_type", "processed"]
    search_fields = ["stripe_event_id", "event_type"]
    readonly_fields = ["stripe_event_id", "event_type", "payload", "processed", "processing_error", "created_at"]
    ordering = ["-created_at"]


@admin.register(StripeAcademyConfig)
class StripeAcademyConfigAdmin(admin.ModelAdmin):
    list_display = ["academy", "default_currency", "is_onboarded", "created_at"]
    list_filter = ["is_onboarded", "default_currency"]
    search_fields = ["academy__name"]
