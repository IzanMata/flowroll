import django_filters

from .models import OpenMatSession


class OpenMatSessionFilter(django_filters.FilterSet):
    date_after = django_filters.DateFilter(field_name="event_date", lookup_expr="gte")
    date_before = django_filters.DateFilter(field_name="event_date", lookup_expr="lte")

    class Meta:
        model = OpenMatSession
        fields = ["academy", "is_cancelled"]
