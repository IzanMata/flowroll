from django.contrib import admin

from .models import AthleteMatchStats


@admin.register(AthleteMatchStats)
class AthleteMatchStatsAdmin(admin.ModelAdmin):
    list_display = [
        "athlete",
        "total_matches",
        "wins",
        "losses",
        "draws",
        "submissions_won",
        "total_points_scored",
        "updated_at",
    ]
    list_filter = ["athlete__academy"]
    search_fields = ["athlete__user__username"]
    readonly_fields = [
        "total_matches",
        "wins",
        "losses",
        "draws",
        "total_points_scored",
        "total_points_conceded",
        "submissions_won",
        "updated_at",
    ]
