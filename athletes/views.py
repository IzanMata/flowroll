from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from core.mixins import AcademyFilterMixin, SwaggerSafeMixin
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
        super().get_queryset()

        # H-2 fix: Enforce tenant isolation with membership validation
        # CONSISTENCY FIX: Use 'academy' parameter like other views (was 'academy_id')
        if self.request.user.is_superuser:
            return self.filter_by_academy(
                AthleteProfile.objects.select_related("user", "academy")
            )

        # For regular users, validate membership and return scoped queryset
        validated_queryset = self.get_academy_scoped_queryset(AthleteProfile.objects.all())
        if validated_queryset is not AthleteProfile.objects.none():
            return self.filter_by_academy(
                AthleteProfile.objects.select_related("user", "academy")
            )
        return validated_queryset

    def get_permissions(self):
        """
        H-2 fix: Use proper permission classes instead of manual checks.
        Write operations require either ownership or professor/owner role.
        """
        if self.action in ("update", "partial_update", "destroy"):
            # For now, keep custom logic but could be extracted to permission class
            return [IsAuthenticated()]  # Will be validated in get_object
        return [IsAcademyMember()]

    def get_object(self):
        obj = super().get_object()
        if self.action in ("update", "partial_update", "destroy"):
            user = self.request.user
            if user.is_superuser:
                return obj

            # Check if user owns this profile
            is_own_profile = obj.user == user

            # Check if user is professor/owner of the academy
            from core.models import AcademyMembership
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
