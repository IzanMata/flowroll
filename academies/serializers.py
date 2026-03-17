from rest_framework import serializers

from .models import Academy


class AcademySerializer(serializers.ModelSerializer):
    """Serializes an Academy for list, detail, create, and update operations."""

    class Meta:
        model = Academy
        fields = ["id", "name", "city", "created_at"]
        # Protegemos la fecha de creación para que nadie la edite enviando un POST
        read_only_fields = ["created_at"]
