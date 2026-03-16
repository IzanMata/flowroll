import django_filters

from .models import MembershipPlan, Seminar, Subscription


class SubscriptionFilter(django_filters.FilterSet):
    class Meta:
        model = Subscription
        fields = ["athlete", "status", "plan__plan_type"]


class SeminarFilter(django_filters.FilterSet):
    event_after = django_filters.DateTimeFilter(field_name="event_date", lookup_expr="gte")
    event_before = django_filters.DateTimeFilter(field_name="event_date", lookup_expr="lte")

    class Meta:
        model = Seminar
        fields = ["academy", "status"]
