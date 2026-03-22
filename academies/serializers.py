from rest_framework import serializers

from .models import Academy


class AcademySerializer(serializers.ModelSerializer):
    """Serializes an Academy for list, detail, create, and update operations."""

    class Meta:
        model = Academy
        fields = [
            "id",
            "name",
            "city",
            "country",
            "description",
            "email",
            "phone",
            "website",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
