from rest_framework import filters, generics, viewsets

from .models import Belt, Technique, TechniqueCategory
from .serializers import (BeltSerializer, TechniqueCategorySerializer,
                          TechniqueSerializer)


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


class TechniqueListView(generics.ListAPIView):
    queryset = Technique.objects.all()
    serializer_class = TechniqueSerializer


class TechniqueDetailView(generics.RetrieveAPIView):
    queryset = Technique.objects.all()
    serializer_class = TechniqueSerializer


class TechniqueCategoryListView(generics.ListAPIView):
    queryset = TechniqueCategory.objects.all()
    serializer_class = TechniqueCategorySerializer


class TechniqueCategoryDetailView(generics.RetrieveAPIView):
    queryset = TechniqueCategory.objects.all()
    serializer_class = TechniqueCategorySerializer


class BeltsListView(generics.ListAPIView):
    queryset = Belt.objects.all()
    serializer_class = BeltSerializer


class BeltDetailView(generics.RetrieveAPIView):
    queryset = Belt.objects.all()
    serializer_class = BeltSerializer
