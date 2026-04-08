"""Serializers for the Academy Analytics Dashboard."""

from rest_framework import serializers


class TopAthleteSerializer(serializers.Serializer):
    athlete_id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    belt = serializers.CharField()
    stripes = serializers.IntegerField()
    mat_hours = serializers.FloatField()


class RevenueSummarySerializer(serializers.Serializer):
    current_month = serializers.CharField()
    previous_month = serializers.CharField()
    change_percent = serializers.FloatField(allow_null=True)
    currency = serializers.CharField()
    by_type = serializers.DictField(child=serializers.CharField())


class AttendanceSummarySerializer(serializers.Serializer):
    this_week = serializers.IntegerField()
    last_week = serializers.IntegerField()
    change_percent = serializers.FloatField(allow_null=True)
    mat_hours_this_month = serializers.FloatField()
    most_popular_class_type = serializers.CharField(allow_null=True)


class MemberSummarySerializer(serializers.Serializer):
    total_active = serializers.IntegerField()
    ready_for_promotion = serializers.IntegerField()
    belt_distribution = serializers.DictField(child=serializers.IntegerField())


class RetentionSummarySerializer(serializers.Serializer):
    active_subscriptions = serializers.IntegerField()
    cancelled_this_month = serializers.IntegerField()
    churn_rate = serializers.FloatField()


class AcademyDashboardSerializer(serializers.Serializer):
    academy_id = serializers.IntegerField()
    generated_at = serializers.CharField()
    period_ref = serializers.CharField()
    revenue = RevenueSummarySerializer()
    attendance = AttendanceSummarySerializer()
    members = MemberSummarySerializer()
    retention = RetentionSummarySerializer()
    top_athletes = TopAthleteSerializer(many=True)
