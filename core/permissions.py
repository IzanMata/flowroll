from rest_framework.permissions import BasePermission, SAFE_METHODS

from core.models import AcademyMembership


def _resolve_academy_pk(view, request):
    """Extract the academy PK from URL kwargs or query params."""
    return view.kwargs.get("academy_pk") or request.query_params.get("academy")


class IsAcademyMember(BasePermission):
    """Allow access to any active member of the academy identified by `academy_pk` in the URL."""

    def has_permission(self, request, view):
        academy_pk = _resolve_academy_pk(view, request)
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
        academy_pk = _resolve_academy_pk(view, request)
        if not academy_pk:
            return False
        return AcademyMembership.objects.filter(
            user=request.user,
            academy_id=academy_pk,
            role__in=self.ALLOWED_ROLES,
            is_active=True,
        ).exists()


class IsAcademyOwner(BasePermission):
    """Allow access only to the academy owner.

    Works with both URL-kwarg based views (academy_pk / academy query param)
    and with AcademyViewSet where the object IS the academy (has_object_permission).
    """

    def has_permission(self, request, view):
        academy_pk = _resolve_academy_pk(view, request)
        if not academy_pk:
            # Defer to has_object_permission for object-detail endpoints
            # (e.g. /api/academies/{pk}/ where the object is the academy itself)
            return request.user and request.user.is_authenticated
        return AcademyMembership.objects.filter(
            user=request.user,
            academy_id=academy_pk,
            role=AcademyMembership.Role.OWNER,
            is_active=True,
        ).exists()

    def has_object_permission(self, request, view, obj):
        """Used when the viewed object IS the Academy (AcademyViewSet)."""
        # Import here to avoid circular imports
        from academies.models import Academy
        if isinstance(obj, Academy):
            return (
                request.user.is_superuser
                or AcademyMembership.objects.filter(
                    user=request.user,
                    academy=obj,
                    role=AcademyMembership.Role.OWNER,
                    is_active=True,
                ).exists()
            )
        return False


class IsSuperAdmin(BasePermission):
    """Allow access only to Django superusers (platform admins)."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_superuser


class ReadOnlyOrSuperAdmin(BasePermission):
    """Allow safe (read) methods to any authenticated user; writes require superuser."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return request.user and request.user.is_superuser
