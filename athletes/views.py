from rest_framework import viewsets

from .models import AthleteProfile
from .serializers import AthleteProfileSerializer


class AthleteProfileViewSet(viewsets.ModelViewSet):
    queryset = AthleteProfile.objects.all()
    serializer_class = AthleteProfileSerializer

    def get_queryset(self):
        """
        Opcional: Filtrar atletas por academia si se pasa en la URL
        Ejemplo: /api/athletes/?academy_id=1
        """
        queryset = AthleteProfile.objects.all()
        academy_id = self.request.query_params.get("academy_id")
        if academy_id is not None:
            queryset = queryset.filter(academy_id=academy_id)
        return queryset
