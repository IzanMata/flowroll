from rest_framework import viewsets

from .models import Academy
from .serializers import AcademySerializer


class AcademyViewSet(viewsets.ModelViewSet):
    queryset = Academy.objects.all()
    serializer_class = AcademySerializer
