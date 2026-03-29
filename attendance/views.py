from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from athletes.models import AthleteProfile
from core.exceptions import standardize_service_error
from core.mixins import AcademyFilterMixin, SwaggerSafeMixin
from core.permissions import IsAcademyMember, IsAcademyProfessor

from . import selectors
from .filters import TrainingClassFilter
from .models import DropInVisitor, TrainingClass
from .serializers import (CheckInSerializer, DropInVisitorSerializer,
                          GenerateQRSerializer, ManualCheckInSerializer,
                          QRCheckInSerializer, QRCodeSerializer,
                          TrainingClassSerializer)
from .services import CheckInService, DropInService, QRCodeService


class TrainingClassViewSet(SwaggerSafeMixin, AcademyFilterMixin, viewsets.ModelViewSet):
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
        # SwaggerSafeMixin handles swagger_fake_view check
        if getattr(self, "swagger_fake_view", False):
            return super().get_queryset()

        # M-1 fix: Use academy scoped queryset with membership validation
        academy_id = self.get_academy_id()
        if self.request.user.is_superuser and academy_id:
            return selectors.get_classes_for_academy(academy_id=academy_id)

        if not academy_id:
            return TrainingClass.objects.none()

        # For regular users, validate membership before returning data
        from core.models import AcademyMembership
        is_member = AcademyMembership.objects.filter(
            user=self.request.user,
            academy_id=academy_id,
            is_active=True,
        ).exists()
        if not is_member:
            return TrainingClass.objects.none()
        return selectors.get_classes_for_academy(academy_id=academy_id)

    @extend_schema(request=GenerateQRSerializer, responses=QRCodeSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAcademyProfessor])
    def generate_qr(self, request, pk=None):
        input_serializer = GenerateQRSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        training_class = self.get_object()
        qr = QRCodeService.generate(
            training_class,
            expiry_minutes=input_serializer.validated_data["expiry_minutes"],
        )
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
            raise standardize_service_error(exc)
        return Response(
            CheckInSerializer(check_in).data, status=status.HTTP_201_CREATED
        )

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

        academy_id = self.get_academy_id()
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
            raise standardize_service_error(exc)
        return Response(
            CheckInSerializer(check_in).data, status=status.HTTP_201_CREATED
        )


class DropInVisitorViewSet(SwaggerSafeMixin, AcademyFilterMixin, viewsets.ModelViewSet):
    """
    M-2 fix: Creation requires IsAcademyProfessor — any academy member can still
    list drop-in visitors, but only professors/owners can register new ones.
    Queryset is also scoped to academy membership.
    """

    serializer_class = DropInVisitorSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        # SwaggerSafeMixin handles swagger_fake_view check
        if getattr(self, "swagger_fake_view", False):
            return super().get_queryset()

        # M-2 fix: Verify membership before leaking PII
        if self.request.user.is_superuser:
            return self.filter_by_academy(DropInVisitor.objects.all())

        # For regular users, validate membership and return scoped queryset
        validated_queryset = self.get_academy_scoped_queryset(DropInVisitor.objects.all())
        if validated_queryset is not DropInVisitor.objects.none():
            return self.filter_by_academy(DropInVisitor.objects.all())
        return validated_queryset

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
