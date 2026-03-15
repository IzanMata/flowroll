from django.contrib.auth.models import User
from rest_framework import serializers

from academies.serializers import AcademySerializer

from .models import AthleteProfile


class AthleteProfileSerializer(serializers.ModelSerializer):

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
