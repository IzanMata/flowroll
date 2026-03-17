from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from athletes.models import AthleteProfile
from core.models import AcademyMembership
from core.permissions import IsAcademyMember, IsAcademyProfessor

from . import selectors
from .filters import CheckInFilter, TrainingClassFilter
from .models import CheckIn, DropInVisitor, TrainingClass
from .serializers import (
    CheckInSerializer,
    DropInVisitorSerializer,
    ManualCheckInSerializer,
    QRCheckInSerializer,
    QRCodeSerializer,
    TrainingClassSerializer,
)
from .services import CheckInService, DropInService, QRCodeService

# Maximum QR code lifetime a professor can request (24 hours)
_MAX_QR_EXPIRY_MINUTES = 1440
_MIN_QR_EXPIRY_MINUTES = 1


class TrainingClassViewSet(viewsets.ModelViewSet):
    """
    M-1 fix: get_queryset validates the requesting user is a member of the
    requested academy before returning any data.
    H-6 fix: manual_checkin scopes athlete and training_class to the same academy.
    M-7 fix: expiry_minutes is clamped to a safe range.
    """

    serializer_class = TrainingClassSerializer
    filterset_class = TrainingClassFilter
    search_fields = ["title", "class_type"]
    ordering_fields = ["scheduled_at", "duration_minutes"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TrainingClass.objects.none()

        academy_id = self.request.query_params.get("academy")
        if not academy_id:
            return TrainingClass.objects.none()

        # M-1 fix: verify the requesting user is an active member before
        # returning any class schedule data.
        user = self.request.user
        if not user.is_superuser:
            is_member = AcademyMembership.objects.filter(
                user=user,
                academy_id=academy_id,
                is_active=True,
            ).exists()
            if not is_member:
                return TrainingClass.objects.none()

        return selectors.get_classes_for_academy(academy_id=academy_id)

    @extend_schema(request=None, responses=QRCodeSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAcademyProfessor])
    def generate_qr(self, request, pk=None):
        training_class = self.get_object()
        # M-7 fix: clamp expiry to a safe range to prevent near-permanent QR codes
        raw_expiry = int(request.data.get("expiry_minutes", 30))
        expiry = max(_MIN_QR_EXPIRY_MINUTES, min(raw_expiry, _MAX_QR_EXPIRY_MINUTES))
        qr = QRCodeService.generate(training_class, expiry_minutes=expiry)
        return Response(QRCodeSerializer(qr).data)

    @extend_schema(
        request=QRCheckInSerializer,
        responses=CheckInSerializer,
        summary="Self check-in via QR code scan",
        description=(
            "Submit a QR token to register the authenticated athlete's attendance. "
            "Returns 400 if the token is expired, invalid, or already used by this athlete."
        ),
    )
    @action(detail=False, methods=["post"])
    def qr_checkin(self, request):
        serializer = QRCheckInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        athlete = get_object_or_404(AthleteProfile, user=request.user)
        try:
            check_in = CheckInService.check_in_via_qr(
                athlete, serializer.validated_data["token"]
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CheckInSerializer(check_in).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ManualCheckInSerializer, responses=CheckInSerializer)
    @action(detail=False, methods=["post"], permission_classes=[IsAcademyProfessor])
    def manual_checkin(self, request):
        """
        H-6 fix: athlete and training_class are both scoped to the academy in the
        query param, preventing a professor from checking in athletes or classes
        that belong to a different academy.
        """
        serializer = ManualCheckInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        academy_id = request.query_params.get("academy")
        if not academy_id:
            return Response(
                {"detail": "academy query param is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # H-6 fix: scope both lookups to the verified academy
        athlete = get_object_or_404(
            AthleteProfile,
            pk=serializer.validated_data["athlete_id"],
            academy_id=academy_id,
        )
        training_class = get_object_or_404(
            TrainingClass,
            pk=serializer.validated_data["training_class_id"],
            academy_id=academy_id,
        )
        try:
            check_in = CheckInService.check_in_manual(athlete, training_class)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CheckInSerializer(check_in).data, status=status.HTTP_201_CREATED)


class DropInVisitorViewSet(viewsets.ModelViewSet):
    """
    M-2 fix: Creation requires IsAcademyProfessor — any academy member can still
    list drop-in visitors, but only professors/owners can register new ones.
    Queryset is also scoped to academy membership.
    """

    serializer_class = DropInVisitorSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return DropInVisitor.objects.none()

        academy_id = self.request.query_params.get("academy")
        if not academy_id:
            return DropInVisitor.objects.none()

        # Verify membership before leaking PII
        user = self.request.user
        if not user.is_superuser:
            is_member = AcademyMembership.objects.filter(
                user=user,
                academy_id=academy_id,
                is_active=True,
            ).exists()
            if not is_member:
                return DropInVisitor.objects.none()

        return DropInVisitor.objects.filter(academy_id=academy_id)

    def get_permissions(self):
        # M-2 fix: only professors/owners may register new drop-in visitors
        if self.action == "create":
            return [IsAcademyProfessor()]
        return [IsAcademyMember()]

    def create(self, request, *args, **kwargs):
        serializer = DropInVisitorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        from academies.models import Academy

        academy = get_object_or_404(Academy, pk=d["academy"].pk)
        visitor = DropInService.register(
            academy=academy,
            first_name=d["first_name"],
            last_name=d["last_name"],
            email=d["email"],
            training_class=d.get("training_class"),
            phone=d.get("phone", ""),
        )
        return Response(
            DropInVisitorSerializer(visitor).data, status=status.HTTP_201_CREATED
        )
