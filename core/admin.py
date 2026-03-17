from django.contrib import admin

from core.models import AcademyMembership, Belt


@admin.register(Belt)
class BeltAdmin(admin.ModelAdmin):
    list_display = ("color", "order")
    ordering = ("order",)


@admin.register(AcademyMembership)
class AcademyMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "academy", "role", "is_active", "joined_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__username", "academy__name")
