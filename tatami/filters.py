import django_filters

from .models import Matchup, TimerPreset


class MatchupFilter(django_filters.FilterSet):
    class Meta:
        model = Matchup
        fields = ["academy", "match_format", "status", "weight_class"]


class TimerPresetFilter(django_filters.FilterSet):
    class Meta:
        model = TimerPreset
        fields = ["academy", "format"]
