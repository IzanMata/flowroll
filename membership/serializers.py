from rest_framework import serializers

from academies.models import Academy

from .models import (DojoTabTransaction, MembershipPlan, Seminar,
                     SeminarRegistration, Subscription)


class MembershipPlanSerializer(serializers.ModelSerializer):
    """Serializes a MembershipPlan for list and detail operations."""

    class Meta:
        model = MembershipPlan
        fields = [
            "id",
            "academy",
            "name",
            "plan_type",
            "price",
            "class_limit",
            "duration_days",
            "is_active",
        ]
        # SEC: academy is set server-side from the URL param; is_active must be
        # toggled through a dedicated admin action, not via free-form PATCH.
        read_only_fields = ["academy", "is_active"]


class SubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializes a Subscription for list and detail operations.

    plan_name is a read-only convenience field. Use SubscriptionService.subscribe()
    to create subscriptions — do not POST to the endpoint directly.
    """

    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "athlete",
            "plan",
            "plan_name",
            "start_date",
            "end_date",
            "status",
            "classes_remaining",
            "created_at",
        ]
        # SEC: status and classes_remaining are managed by SubscriptionService
        # (cancel, consume_class_pass, expire_stale). Direct writes would let
        # a user self-reactivate a cancelled plan or inflate remaining classes.
        read_only_fields = ["status", "classes_remaining", "end_date", "created_at"]


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
    """
    Serializes a dojo tab transaction (DEBIT or CREDIT).

    billed and created_at are managed by DojoTabService and are read-only.
    Use DojoTabService.charge() or DojoTabService.credit() to create transactions.
    """

    class Meta:
        model = DojoTabTransaction
        fields = [
            "id",
            "athlete",
            "academy",
            "transaction_type",
            "amount",
            "description",
            "billed",
            "created_at",
        ]
        read_only_fields = ["billed", "created_at"]


class SeminarSerializer(serializers.ModelSerializer):
    """
    Serializes a Seminar for list and detail operations.

    spots_remaining is a model property (capacity − confirmed registrations)
    exposed as a read-only field. Use SeminarService.register() to book a spot.
    """

    spots_remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = Seminar
        fields = [
            "id",
            "academy",
            "title",
            "instructor_name",
            "description",
            "event_date",
            "capacity",
            "price",
            "status",
            "spots_remaining",
        ]
        # SEC: academy is set server-side from the view; status transitions
        # (OPEN → FULL → CANCELLED) are driven by SeminarService, not free writes.
        read_only_fields = ["academy", "status"]


class EnrollmentSerializer(serializers.Serializer):
    """Input serializer for the enrollment endpoint."""

    academy = serializers.PrimaryKeyRelatedField(
        queryset=Academy.objects.filter(is_active=True),
        help_text="ID of the academy to join.",
    )
    plan = serializers.PrimaryKeyRelatedField(
        queryset=MembershipPlan.objects.filter(is_active=True),
        help_text="ID of the membership plan to subscribe to.",
    )


class SeminarRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializes a seminar registration record.

    status (CONFIRMED, WAITLISTED, CANCELLED) is managed by SeminarService
    and is read-only. Use SeminarService.register() and cancel_registration()
    to drive status transitions.
    """

    athlete_name = serializers.CharField(source="athlete.user.username", read_only=True)
    seminar_title = serializers.CharField(source="seminar.title", read_only=True)

    class Meta:
        model = SeminarRegistration
        fields = [
            "id",
            "seminar",
            "seminar_title",
            "athlete",
            "athlete_name",
            "status",
            "payment_status",
            "notes",
            "created_at",
        ]
        read_only_fields = ["status", "created_at"]
