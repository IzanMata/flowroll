from rest_framework import serializers

from core.models import AcademyMembership

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


class AcademyMembershipSerializer(serializers.ModelSerializer):
    """Read serializer for listing academy members."""

    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    class Meta:
        model = AcademyMembership
        fields = ["user", "username", "email", "first_name", "last_name", "role", "joined_at"]
        read_only_fields = fields


class AddMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=[AcademyMembership.Role.STUDENT, AcademyMembership.Role.PROFESSOR]
    )


class ChangeRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=AcademyMembership.Role.choices)
