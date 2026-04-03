from django.contrib import admin

from .models import Tournament, TournamentDivision, TournamentMatch, TournamentParticipant


class TournamentDivisionInline(admin.TabularInline):
    model = TournamentDivision
    extra = 0


class TournamentParticipantInline(admin.TabularInline):
    model = TournamentParticipant
    extra = 0
    readonly_fields = ["belt_at_registration", "weight_at_registration", "seed"]


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ["name", "academy", "date", "status", "format"]
    list_filter = ["status", "format", "academy"]
    search_fields = ["name", "location"]
    inlines = [TournamentDivisionInline, TournamentParticipantInline]


@admin.register(TournamentDivision)
class TournamentDivisionAdmin(admin.ModelAdmin):
    list_display = ["name", "tournament", "belt_min", "belt_max", "weight_min", "weight_max"]
    list_filter = ["tournament"]


@admin.register(TournamentParticipant)
class TournamentParticipantAdmin(admin.ModelAdmin):
    list_display = ["athlete", "tournament", "division", "status", "seed"]
    list_filter = ["status", "tournament"]
    readonly_fields = ["belt_at_registration", "weight_at_registration"]


@admin.register(TournamentMatch)
class TournamentMatchAdmin(admin.ModelAdmin):
    list_display = ["tournament", "division", "round_number", "athlete_a", "athlete_b", "winner", "is_finished"]
    list_filter = ["tournament", "is_finished", "round_number"]
    readonly_fields = ["winner", "score_a", "score_b", "is_finished"]
