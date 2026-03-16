from django.contrib import admin

from .models import Matchup, TimerPreset, TimerSession, WeightClass


@admin.register(WeightClass)
class WeightClassAdmin(admin.ModelAdmin):
    list_display = ["name", "gender", "min_weight", "max_weight"]


@admin.register(TimerPreset)
class TimerPresetAdmin(admin.ModelAdmin):
    list_display = ["name", "academy", "format", "round_duration_seconds", "rounds"]


@admin.register(TimerSession)
class TimerSessionAdmin(admin.ModelAdmin):
    list_display = ["preset", "status", "current_round", "started_at"]


@admin.register(Matchup)
class MatchupAdmin(admin.ModelAdmin):
    list_display = ["athlete_a", "athlete_b", "match_format", "round_number", "status", "winner"]
    list_filter = ["match_format", "status"]
