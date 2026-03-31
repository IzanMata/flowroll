from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from academies.models import Academy
from core.mixins import AcademyFilterMixin, SwaggerSafeMixin
from core.models import AcademyMembership
from core.permissions import IsAcademyMember

from .models import AthleteProfile
from .serializers import AthleteProfileSerializer


class AthleteProfileViewSet(SwaggerSafeMixin, AcademyFilterMixin, viewsets.ModelViewSet):
    """
    H-2 fix: Enforce tenant isolation — only return athletes that belong
    to an academy the requesting user is an active member of.
    Write operations are restricted: a user may only edit their own profile
    unless they are a professor/owner of the athlete's academy.
    """

    serializer_class = AthleteProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # SwaggerSafeMixin handles swagger_fake_view check
        if getattr(self, "swagger_fake_view", False):
            return super().get_queryset()

        if self.request.user.is_superuser:
            return self.filter_by_academy(
                AthleteProfile.objects.select_related("user", "academy")
            )

        academy_id = self.get_academy_id()
        if not academy_id:
            return AthleteProfile.objects.none()

        # Explicit membership check — avoids the broken `is not queryset.none()`
        # identity comparison (two .none() calls are never the same object).
        if not AcademyMembership.objects.filter(
            user=self.request.user, academy_id=academy_id, is_active=True
        ).exists():
            return AthleteProfile.objects.none()

        return AthleteProfile.objects.filter(
            academy_id=academy_id
        ).select_related("user", "academy")

    def get_permissions(self):
        """
        Write operations require academy membership (enforced here) plus
        ownership-or-professor validation (enforced in get_object).
        Read operations also require academy membership when academy is specified.
        Superusers bypass academy membership checks.
        """
        if self.action in ("update", "partial_update", "destroy"):
            if self.request.user.is_superuser:
                return [IsAuthenticated()]
            return [IsAcademyMember()]

        # For read operations, require academy membership only if academy is specified
        academy_id = self.kwargs.get("academy_pk") or self.request.query_params.get("academy")
        if academy_id:
            return [IsAcademyMember()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        academy_id = self.get_academy_id()
        if academy_id:
            academy = get_object_or_404(Academy, pk=academy_id)
            serializer.save(academy=academy)
        else:
            serializer.save()

    def get_object(self):
        obj = super().get_object()
        if self.action in ("update", "partial_update", "destroy"):
            user = self.request.user
            if user.is_superuser:
                return obj

            # Check if user owns this profile
            is_own_profile = obj.user == user

            # Check if user is professor/owner of the academy
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
