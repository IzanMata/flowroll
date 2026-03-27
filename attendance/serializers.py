from rest_framework import serializers

from .models import CheckIn, DropInVisitor, QRCode, TrainingClass


class TrainingClassSerializer(serializers.ModelSerializer):
    """
    Serializes a TrainingClass for list and detail responses.

    attendance_count is populated by the DB-level annotation added in
    attendance.selectors.get_classes_for_academy() — it reads an annotated
    integer rather than issuing a COUNT query per row (L-3 fix).
    """

    professor_username = serializers.CharField(
        source="professor.username", read_only=True
    )
    # L-3 fix: read from a pre-computed annotation instead of issuing a COUNT
    # query per object (N+1 problem).  The annotation is added by
    # attendance/selectors.py::get_classes_for_academy().
    attendance_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = TrainingClass
        fields = [
            "id",
            "academy",
            "title",
            "class_type",
            "professor",
            "professor_username",
            "scheduled_at",
            "duration_minutes",
            "max_capacity",
            "notes",
            "attendance_count",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class QRCodeSerializer(serializers.ModelSerializer):
    """
    Serializes a QRCode token for the generate_qr response.

    is_valid exposes the model property (is_active AND not expired) as a
    convenience field so clients can skip the datetime comparison.
    """

    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = QRCode
        fields = [
            "id",
            "training_class",
            "token",
            "expires_at",
            "is_active",
            "is_valid",
        ]
        read_only_fields = ["token", "created_at"]


class CheckInSerializer(serializers.ModelSerializer):
    """Serializes a CheckIn record for the qr_checkin and manual_checkin responses."""

    athlete_username = serializers.CharField(
        source="athlete.user.username", read_only=True
    )

    class Meta:
        model = CheckIn
        fields = [
            "id",
            "athlete",
            "athlete_username",
            "training_class",
            "method",
            "checked_in_at",
        ]
        read_only_fields = ["checked_in_at"]


class GenerateQRSerializer(serializers.Serializer):
    """Input serializer for QR code generation. Rejects out-of-range expiry values."""

    expiry_minutes = serializers.IntegerField(
        default=30,
        min_value=1,
        max_value=1440,
        help_text="QR code lifetime in minutes (1–1440). Defaults to 30.",
    )


class QRCheckInSerializer(serializers.Serializer):
    """Input serializer for QR-based check-in."""

    token = serializers.CharField(max_length=64)


class ManualCheckInSerializer(serializers.Serializer):
    """Input serializer for professor-triggered manual check-in."""

    athlete_id = serializers.IntegerField(min_value=1)
    training_class_id = serializers.IntegerField(min_value=1)


class DropInVisitorSerializer(serializers.ModelSerializer):
    """
    Serializes a DropInVisitor for list, detail, and create operations.

    access_token and status are set by DropInService on creation and are
    read-only through the API. status transitions (PENDING → ACTIVE → EXPIRED)
    are managed by DropInService.expire_stale() via Celery.
    """

    class Meta:
        model = DropInVisitor
        fields = [
            "id",
            "academy",
            "first_name",
            "last_name",
            "email",
            "phone",
            "training_class",
            "access_token",
            "expires_at",
            "status",
            "created_at",
        ]
        read_only_fields = ["access_token", "status", "created_at"]
