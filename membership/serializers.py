from rest_framework import serializers

from .models import (
    DojoTabTransaction,
    MembershipPlan,
    SeminarRegistration,
    Seminar,
    Subscription,
)
from .services import PromotionReadiness


class MembershipPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = MembershipPlan
        fields = [
            "id", "academy", "name", "plan_type", "price",
            "class_limit", "duration_days", "is_active",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id", "athlete", "plan", "plan_name", "start_date",
            "end_date", "status", "classes_remaining", "created_at",
        ]
        read_only_fields = ["created_at"]


class PromotionReadinessSerializer(serializers.Serializer):
    """Read-only serializer for the PromotionReadiness dataclass."""
    is_ready = serializers.BooleanField()
    mat_hours_ok = serializers.BooleanField()
    months_at_belt_ok = serializers.BooleanField()
    stripes_ok = serializers.BooleanField()
    current_mat_hours = serializers.FloatField()
    required_mat_hours = serializers.FloatField()
    current_months = serializers.IntegerField()
    required_months = serializers.IntegerField()
    current_stripes = serializers.IntegerField()
    required_stripes = serializers.IntegerField()
    message = serializers.CharField()


class DojoTabTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DojoTabTransaction
        fields = [
            "id", "athlete", "academy", "transaction_type",
            "amount", "description", "billed", "created_at",
        ]
        read_only_fields = ["billed", "created_at"]


class SeminarSerializer(serializers.ModelSerializer):
    spots_remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = Seminar
        fields = [
            "id", "academy", "title", "instructor_name", "description",
            "event_date", "capacity", "price", "status", "spots_remaining",
        ]


class SeminarRegistrationSerializer(serializers.ModelSerializer):
    athlete_name = serializers.CharField(source="athlete.user.username", read_only=True)
    seminar_title = serializers.CharField(source="seminar.title", read_only=True)

    class Meta:
        model = SeminarRegistration
        fields = [
            "id", "seminar", "seminar_title", "athlete", "athlete_name",
            "status", "payment_status", "notes", "created_at",
        ]
        read_only_fields = ["status", "created_at"]
