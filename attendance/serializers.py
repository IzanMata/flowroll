from rest_framework import serializers

from .models import CheckIn, DropInVisitor, QRCode, TrainingClass


class TrainingClassSerializer(serializers.ModelSerializer):
    professor_username = serializers.CharField(source="professor.username", read_only=True)
    # L-3 fix: read from a pre-computed annotation instead of issuing a COUNT
    # query per object (N+1 problem).  The annotation is added by
    # attendance/selectors.py::get_classes_for_academy().
    attendance_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = TrainingClass
        fields = [
            "id", "academy", "title", "class_type", "professor", "professor_username",
            "scheduled_at", "duration_minutes", "max_capacity", "notes",
            "attendance_count", "created_at",
        ]
        read_only_fields = ["created_at"]


class QRCodeSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = QRCode
        fields = ["id", "training_class", "token", "expires_at", "is_active", "is_valid"]
        read_only_fields = ["token", "created_at"]


class CheckInSerializer(serializers.ModelSerializer):
    athlete_username = serializers.CharField(source="athlete.user.username", read_only=True)

    class Meta:
        model = CheckIn
        fields = ["id", "athlete", "athlete_username", "training_class", "method", "checked_in_at"]
        read_only_fields = ["checked_in_at"]


class QRCheckInSerializer(serializers.Serializer):
    """Input serializer for QR-based check-in."""
    token = serializers.CharField(max_length=64)


class ManualCheckInSerializer(serializers.Serializer):
    """Input serializer for professor-triggered manual check-in."""
    athlete_id = serializers.IntegerField()
    training_class_id = serializers.IntegerField()


class DropInVisitorSerializer(serializers.ModelSerializer):
    class Meta:
        model = DropInVisitor
        fields = [
            "id", "academy", "first_name", "last_name", "email", "phone",
            "training_class", "access_token", "expires_at", "status", "created_at",
        ]
        read_only_fields = ["access_token", "status", "created_at"]
