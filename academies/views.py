from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.mixins import SwaggerSafeMixin
from core.models import AcademyMembership
from core.permissions import IsAcademyOwner

from .models import Academy
from .serializers import AcademySerializer


class AcademyViewSet(SwaggerSafeMixin, viewsets.ModelViewSet):
    """
    H-1 fix: Scope queryset to the user's own academies and enforce
    ownership for mutating operations.
    """

    serializer_class = AcademySerializer

    def get_queryset(self):
        """
        Return only academies the requesting user is an active member of.
        Superusers see everything.
        H-1 fix: SwaggerSafeMixin handles swagger_fake_view check.
        """
        # SwaggerSafeMixin handles swagger_fake_view check
        super().get_queryset()

        user = self.request.user
        if user.is_superuser:
            return Academy.objects.all()

        # H-1 fix: Scope to user's academies
        member_ids = AcademyMembership.objects.filter(
            user=user,
            is_active=True,
        ).values_list("academy_id", flat=True)
        return Academy.objects.filter(pk__in=member_ids)

    def get_permissions(self):
        """
        - list / retrieve / create → authenticated users only
        - update / partial_update / destroy → academy owner or superuser
        """
        if self.action in ("update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsAcademyOwner()]
        return [IsAuthenticated()]

    def get_object(self):
        """Ensure get_object triggers check_object_permissions for owner guard."""
        obj = super().get_object()
        self.check_object_permissions(self.request, obj)
        return obj
