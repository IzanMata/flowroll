from rest_framework.permissions import BasePermission

from core.models import AcademyMembership


class IsAcademyMember(BasePermission):
    """Allow access to any active member of the academy identified by `academy_pk` in the URL."""

    def has_permission(self, request, view):
        academy_pk = view.kwargs.get("academy_pk") or request.query_params.get("academy")
        if not academy_pk:
            return False
        return AcademyMembership.objects.filter(
            user=request.user,
            academy_id=academy_pk,
            is_active=True,
        ).exists()


class IsAcademyProfessor(BasePermission):
    """Allow access only to professors (or owners) of the resolved academy."""

    ALLOWED_ROLES = {AcademyMembership.Role.PROFESSOR, AcademyMembership.Role.OWNER}

    def has_permission(self, request, view):
        academy_pk = view.kwargs.get("academy_pk") or request.query_params.get("academy")
        if not academy_pk:
            return False
        return AcademyMembership.objects.filter(
            user=request.user,
            academy_id=academy_pk,
            role__in=self.ALLOWED_ROLES,
            is_active=True,
        ).exists()


class IsAcademyOwner(BasePermission):
    """Allow access only to the academy owner."""

    def has_permission(self, request, view):
        academy_pk = view.kwargs.get("academy_pk") or request.query_params.get("academy")
        if not academy_pk:
            return False
        return AcademyMembership.objects.filter(
            user=request.user,
            academy_id=academy_pk,
            role=AcademyMembership.Role.OWNER,
            is_active=True,
        ).exists()


class IsSuperAdmin(BasePermission):
    """Allow access only to Django superusers (platform admins)."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_superuser
