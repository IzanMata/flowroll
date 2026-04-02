from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.mixins import SwaggerSafeMixin
from core.models import AcademyMembership
from core.permissions import IsAcademyOwner
from membership.models import MembershipPlan
from membership.serializers import MembershipPlanSerializer

from .filters import PublicAcademyFilter
from .models import Academy
from .serializers import (AcademyMembershipSerializer, AcademySerializer,
                           AddMemberSerializer, ChangeRoleSerializer)
from .services import AcademyMemberService, AcademyService


class PublicAcademyListView(generics.ListAPIView):
    """
    List all active academies — no authentication required.

    Filtering:
      ?search=<term>     — searches name, city, country (case-insensitive contains)
      ?city=<term>       — filter by city (case-insensitive contains)
      ?country=<term>    — filter by country (case-insensitive contains)
    """

    permission_classes = [AllowAny]
    serializer_class = AcademySerializer
    queryset = Academy.objects.filter(is_active=True)
    filterset_class = PublicAcademyFilter
    search_fields = ["name", "city", "country"]


class PublicAcademyPlansView(generics.ListAPIView):
    """List active membership plans for a given academy — no authentication required."""

    permission_classes = [AllowAny]
    serializer_class = MembershipPlanSerializer

    def get_queryset(self):
        return MembershipPlan.objects.filter(
            academy_id=self.kwargs["pk"], is_active=True
        )


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
        if getattr(self, "swagger_fake_view", False):
            return super().get_queryset()

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

    def perform_create(self, serializer):
        """Create the academy and automatically grant the creator the OWNER role."""
        AcademyService.create_academy(
            user=self.request.user,
            **serializer.validated_data,
        )

    def get_object(self):
        """Ensure get_object triggers check_object_permissions for owner guard."""
        obj = super().get_object()
        self.check_object_permissions(self.request, obj)
        return obj


class AcademyMemberListView(APIView):
    """
    GET  /api/academies/{id}/members/ — list active members (OWNER/PROFESSOR)
    POST /api/academies/{id}/members/ — add a user by email (OWNER only)
    """

    def _get_academy_or_404(self, pk, user):
        try:
            academy = Academy.objects.get(pk=pk)
        except Academy.DoesNotExist:
            return None, Response({"detail": "Academy not found."}, status=404)
        if not AcademyMembership.objects.filter(user=user, academy=academy, is_active=True).exists():
            return None, Response({"detail": "Not found."}, status=404)
        return academy, None

    def get(self, request, pk):
        academy, err = self._get_academy_or_404(pk, request.user)
        if err:
            return err
        memberships = (
            AcademyMembership.objects.filter(academy=academy, is_active=True)
            .select_related("user")
            .order_by("user__username")
        )
        return Response(AcademyMembershipSerializer(memberships, many=True).data)

    def post(self, request, pk):
        academy, err = self._get_academy_or_404(pk, request.user)
        if err:
            return err
        if not AcademyMembership.objects.filter(
            user=request.user, academy=academy, role=AcademyMembership.Role.OWNER, is_active=True
        ).exists():
            return Response({"detail": "Only the academy owner can add members."}, status=403)

        serializer = AddMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            membership = AcademyMemberService.add_member(
                academy=academy,
                email=serializer.validated_data["email"],
                role=serializer.validated_data["role"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(AcademyMembershipSerializer(membership).data, status=201)


class AcademyMemberDetailView(APIView):
    """
    PATCH  /api/academies/{id}/members/{user_id}/ — change role (OWNER only)
    DELETE /api/academies/{id}/members/{user_id}/ — remove member (OWNER only)
    """

    def _get_academy_and_check_owner(self, pk, user):
        try:
            academy = Academy.objects.get(pk=pk)
        except Academy.DoesNotExist:
            return None, Response({"detail": "Academy not found."}, status=404)
        if not AcademyMembership.objects.filter(
            user=user, academy=academy, role=AcademyMembership.Role.OWNER, is_active=True
        ).exists():
            return None, Response({"detail": "Only the academy owner can manage members."}, status=403)
        return academy, None

    def patch(self, request, pk, user_id):
        academy, err = self._get_academy_and_check_owner(pk, request.user)
        if err:
            return err
        serializer = ChangeRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            membership = AcademyMemberService.change_role(
                academy=academy,
                target_user_id=user_id,
                new_role=serializer.validated_data["role"],
                requesting_user=request.user,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(AcademyMembershipSerializer(membership).data)

    def delete(self, request, pk, user_id):
        academy, err = self._get_academy_and_check_owner(pk, request.user)
        if err:
            return err
        try:
            AcademyMemberService.remove_member(
                academy=academy,
                target_user_id=user_id,
                requesting_user=request.user,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(status=204)
