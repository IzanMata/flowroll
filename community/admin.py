from django.contrib import admin

from .models import Achievement, AthleteAchievement, OpenMatRSVP, OpenMatSession


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ["name", "trigger_type", "trigger_value"]


@admin.register(AthleteAchievement)
class AthleteAchievementAdmin(admin.ModelAdmin):
    list_display = ["athlete", "achievement", "awarded_by", "created_at"]


@admin.register(OpenMatSession)
class OpenMatSessionAdmin(admin.ModelAdmin):
    list_display = ["title", "academy", "event_date", "start_time", "is_cancelled"]
    list_filter = ["is_cancelled", "academy"]


@admin.register(OpenMatRSVP)
class OpenMatRSVPAdmin(admin.ModelAdmin):
    list_display = ["athlete", "session", "status"]
    list_filter = ["status"]
