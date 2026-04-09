from rest_framework import serializers

from academies.serializers import AcademySerializer

from .models import AthleteProfile
from .services import PromotionReadiness


class AthleteProfileSerializer(serializers.ModelSerializer):
    """
    Serializes an AthleteProfile for list, detail, create, and update operations.

    Flattens username and email from the related User record as read-only fields.
    Nests the full AcademySerializer under academy_detail for read convenience
    while keeping academy as a writable FK id for writes.
    """

    username = serializers.ReadOnlyField(source="user.username")
    email = serializers.ReadOnlyField(source="user.email")

    academy_detail = AcademySerializer(source="academy", read_only=True)

    class Meta:
        model = AthleteProfile
        fields = [
            "id",
            "user",
            "username",
            "email",
            "academy",
            "academy_detail",
            "role",
            "belt",
            "stripes",
            "weight",
            "mat_hours",
        ]
        read_only_fields = ["user", "role", "academy", "mat_hours"]


class PromotionReadinessSerializer(serializers.Serializer):
    athlete_id = serializers.IntegerField()
    current_belt = serializers.CharField()
    next_belt = serializers.CharField(allow_null=True)
    requirement_found = serializers.BooleanField()
    is_ready = serializers.BooleanField()
    mat_hours_ok = serializers.BooleanField()
    mat_hours_current = serializers.FloatField()
    mat_hours_required = serializers.FloatField()
    months_ok = serializers.BooleanField()
    months_current = serializers.FloatField()
    months_required = serializers.IntegerField()
    stripes_ok = serializers.BooleanField()
    stripes_current = serializers.IntegerField()
    stripes_required = serializers.IntegerField()
