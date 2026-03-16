from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from athletes.models import AthleteProfile
from core.permissions import IsAcademyProfessor

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


class TrainingClassViewSet(viewsets.ModelViewSet):
    serializer_class = TrainingClassSerializer
    filterset_class = TrainingClassFilter
    search_fields = ["title", "class_type"]
    ordering_fields = ["scheduled_at", "duration_minutes"]

    def get_queryset(self):
        return selectors.get_classes_for_academy(
            academy_id=self.request.query_params.get("academy"),
        ) if self.request.query_params.get("academy") else TrainingClass.objects.none()

    @extend_schema(request=None, responses=QRCodeSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAcademyProfessor])
    def generate_qr(self, request, pk=None):
        training_class = self.get_object()
        expiry = int(request.data.get("expiry_minutes", 30))
        qr = QRCodeService.generate(training_class, expiry_minutes=expiry)
        return Response(QRCodeSerializer(qr).data)

    @extend_schema(request=QRCheckInSerializer, responses=CheckInSerializer)
    @action(detail=False, methods=["post"])
    def qr_checkin(self, request):
        serializer = QRCheckInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        athlete = get_object_or_404(AthleteProfile, user=request.user)
        try:
            check_in = CheckInService.check_in_via_qr(athlete, serializer.validated_data["token"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CheckInSerializer(check_in).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ManualCheckInSerializer, responses=CheckInSerializer)
    @action(detail=False, methods=["post"], permission_classes=[IsAcademyProfessor])
    def manual_checkin(self, request):
        serializer = ManualCheckInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        athlete = get_object_or_404(AthleteProfile, pk=serializer.validated_data["athlete_id"])
        training_class = get_object_or_404(TrainingClass, pk=serializer.validated_data["training_class_id"])
        try:
            check_in = CheckInService.check_in_manual(athlete, training_class)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CheckInSerializer(check_in).data, status=status.HTTP_201_CREATED)


class DropInVisitorViewSet(viewsets.ModelViewSet):
    serializer_class = DropInVisitorSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return DropInVisitor.objects.filter(
            academy_id=self.request.query_params.get("academy")
        ) if self.request.query_params.get("academy") else DropInVisitor.objects.none()

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
        return Response(DropInVisitorSerializer(visitor).data, status=status.HTTP_201_CREATED)
