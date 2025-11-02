from rest_framework import filters, viewsets

from .models import Belt, Technique, TechniqueCategory, TechniqueVariation
from .serializers import (BeltSerializer, TechniqueCategorySerializer,
                          TechniqueSerializer, TechniqueVariationSerializer)


class TechniqueViewSet(viewsets.ModelViewSet):
    queryset = Technique.objects.prefetch_related(
        "categories", "variations", "leads_to", "comes_from", "min_belt"
    )
    serializer_class = TechniqueSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description", "categories__name"]
    ordering_fields = ["difficulty", "name"]


class TechniqueCategoryViewSet(viewsets.ModelViewSet):
    queryset = TechniqueCategory.objects.all()
    serializer_class = TechniqueCategorySerializer


class BeltViewSet(viewsets.ModelViewSet):
    queryset = Belt.objects.all()
    serializer_class = BeltSerializer


class TechniqueVariationViewSet(viewsets.ModelViewSet):
    queryset = TechniqueVariation.objects.select_related("technique")
    serializer_class = TechniqueVariationSerializer
