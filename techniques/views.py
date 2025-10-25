from rest_framework import generics

from .models import Technique, TechniqueCategory
from .serializers import TechniqueCategorySerializer, TechniqueSerializer


class TechniqueListView(generics.ListAPIView):
    queryset = Technique.objects.all()
    serializer_class = TechniqueSerializer


class TechniqueDetailView(generics.RetrieveAPIView):
    queryset = Technique.objects.all()
    serializer_class = TechniqueSerializer


class TechniqueCategoryListView(generics.ListAPIView):
    queryset = TechniqueCategory.objects.all()
    serializer_class = TechniqueCategorySerializer
