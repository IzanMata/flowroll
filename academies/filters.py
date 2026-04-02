import django_filters

from .models import Academy


class PublicAcademyFilter(django_filters.FilterSet):
    city = django_filters.CharFilter(field_name="city", lookup_expr="icontains")
    country = django_filters.CharFilter(field_name="country", lookup_expr="icontains")

    class Meta:
        model = Academy
        fields = ["city", "country"]
