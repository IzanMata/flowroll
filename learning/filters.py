import django_filters

from .models import SparringNote, VideoLibraryItem


class VideoLibraryFilter(django_filters.FilterSet):
    class Meta:
        model = VideoLibraryItem
        fields = ["academy", "source", "visibility", "technique"]


class SparringNoteFilter(django_filters.FilterSet):
    date_after = django_filters.DateFilter(field_name="session_date", lookup_expr="gte")
    date_before = django_filters.DateFilter(field_name="session_date", lookup_expr="lte")

    class Meta:
        model = SparringNote
        fields = ["athlete", "training_class"]
