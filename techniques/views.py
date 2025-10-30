from rest_framework import generics, viewsets

from .models import Technique, TechniqueCategory
from .serializers import TechniqueCategorySerializer, TechniqueSerializer


class TechniqueViewSet(viewsets.ModelViewSet):
    queryset = Technique.objects.all()
    serializer_class = TechniqueSerializer


class TechniqueCategoryViewSet(viewsets.ModelViewSet):
    queryset = TechniqueCategory.objects.all()
    serializer_class = TechniqueCategorySerializer


class TechniqueListView(generics.ListAPIView):
    queryset = Technique.objects.all()
    serializer_class = TechniqueSerializer


class TechniqueDetailView(generics.RetrieveAPIView):
    queryset = Technique.objects.all()
    serializer_class = TechniqueSerializer


class TechniqueCategoryListView(generics.ListAPIView):
    queryset = TechniqueCategory.objects.all()
    serializer_class = TechniqueCategorySerializer
