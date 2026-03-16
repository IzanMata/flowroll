import django_filters

from .models import CheckIn, TrainingClass


class TrainingClassFilter(django_filters.FilterSet):
    scheduled_after = django_filters.DateTimeFilter(field_name="scheduled_at", lookup_expr="gte")
    scheduled_before = django_filters.DateTimeFilter(field_name="scheduled_at", lookup_expr="lte")

    class Meta:
        model = TrainingClass
        fields = ["academy", "class_type", "professor"]


class CheckInFilter(django_filters.FilterSet):
    class Meta:
        model = CheckIn
        fields = ["training_class", "athlete", "method"]
