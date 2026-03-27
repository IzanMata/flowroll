from rest_framework import serializers

from academies.serializers import AcademySerializer

from .models import AthleteProfile


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
        ]
        read_only_fields = ["user"]
