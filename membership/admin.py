from django.contrib import admin

from .models import (DojoTabBalance, DojoTabTransaction, MembershipPlan,
                     PromotionRequirement, Seminar, SeminarRegistration,
                     Subscription)


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ["name", "academy", "plan_type", "price", "is_active"]
    list_filter = ["plan_type", "is_active"]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["athlete", "plan", "status", "start_date", "end_date"]
    list_filter = ["status"]


@admin.register(PromotionRequirement)
class PromotionRequirementAdmin(admin.ModelAdmin):
    list_display = [
        "belt",
        "academy",
        "min_mat_hours",
        "min_months_at_belt",
        "min_stripes_before_promotion",
    ]


@admin.register(DojoTabTransaction)
class DojoTabTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "athlete",
        "academy",
        "transaction_type",
        "amount",
        "description",
        "billed",
    ]
    list_filter = ["transaction_type", "billed"]


@admin.register(DojoTabBalance)
class DojoTabBalanceAdmin(admin.ModelAdmin):
    list_display = ["athlete", "academy", "balance"]


@admin.register(Seminar)
class SeminarAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "academy",
        "instructor_name",
        "event_date",
        "capacity",
        "status",
    ]
    list_filter = ["status"]


@admin.register(SeminarRegistration)
class SeminarRegistrationAdmin(admin.ModelAdmin):
    list_display = ["athlete", "seminar", "status", "payment_status"]
    list_filter = ["status", "payment_status"]
