from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from core.models import AcademyMembership

from .models import AthleteProfile
from .serializers import AthleteProfileSerializer


class AthleteProfileViewSet(viewsets.ModelViewSet):
    """
    H-2 fix: Enforce tenant isolation — only return athletes that belong
    to an academy the requesting user is an active member of.
    Write operations are restricted: a user may only edit their own profile
    unless they are a professor/owner of the athlete's academy.
    """

    serializer_class = AthleteProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AthleteProfile.objects.none()

        academy_id = self.request.query_params.get("academy_id")
        if not academy_id:
            return AthleteProfile.objects.none()

        user = self.request.user
        # Verify the requesting user is a member of the requested academy
        if not user.is_superuser:
            is_member = AcademyMembership.objects.filter(
                user=user,
                academy_id=academy_id,
                is_active=True,
            ).exists()
            if not is_member:
                return AthleteProfile.objects.none()

        return (
            AthleteProfile.objects.filter(academy_id=academy_id)
            .select_related("user", "academy")
        )

    def get_object(self):
        obj = super().get_object()
        if self.action in ("update", "partial_update", "destroy"):
            user = self.request.user
            if user.is_superuser:
                return obj
            is_own_profile = obj.user == user
            is_professor_or_owner = AcademyMembership.objects.filter(
                user=user,
                academy=obj.academy,
                role__in=[
                    AcademyMembership.Role.PROFESSOR,
                    AcademyMembership.Role.OWNER,
                ],
                is_active=True,
            ).exists()
            if not (is_own_profile or is_professor_or_owner):
                raise PermissionDenied(
                    "You do not have permission to modify this athlete profile."
                )
        return obj
