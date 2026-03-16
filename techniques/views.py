from rest_framework import filters, viewsets

from core.models import Belt
from core.permissions import ReadOnlyOrSuperAdmin

from .models import Technique, TechniqueCategory, TechniqueVariation
from .serializers import (
    BeltSerializer,
    TechniqueCategorySerializer,
    TechniqueSerializer,
    TechniqueVariationSerializer,
)


class TechniqueViewSet(viewsets.ModelViewSet):
    """
    H-3 fix: Technique library is platform-wide (no academy FK).
    Reads are open to any authenticated user; writes require superuser.
    """

    queryset = Technique.objects.prefetch_related(
        "categories", "variations", "leads_to", "comes_from", "min_belt"
    )
    serializer_class = TechniqueSerializer
    permission_classes = [ReadOnlyOrSuperAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description", "categories__name"]
    ordering_fields = ["difficulty", "name"]


class TechniqueCategoryViewSet(viewsets.ModelViewSet):
    """H-3 fix: reads open to any authenticated user; writes require superuser."""

    queryset = TechniqueCategory.objects.all()
    serializer_class = TechniqueCategorySerializer
    permission_classes = [ReadOnlyOrSuperAdmin]


class BeltViewSet(viewsets.ReadOnlyModelViewSet):
    """
    H-3 fix: Belt records are foundational to the promotion system.
    Read-only — only managed via Django admin / data migrations.
    """

    queryset = Belt.objects.all()
    serializer_class = BeltSerializer


class TechniqueVariationViewSet(viewsets.ModelViewSet):
    """H-3 fix: reads open to any authenticated user; writes require superuser."""

    queryset = TechniqueVariation.objects.select_related("technique")
    serializer_class = TechniqueVariationSerializer
    permission_classes = [ReadOnlyOrSuperAdmin]
