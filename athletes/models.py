from django.contrib.auth import models as auth_models
from django.db import models

from academies.models import Academy
from core.models import Belt


class AthleteProfile(models.Model):

    class RoleChoices(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        PROFESSOR = "PROFESSOR", "Professor"

    user = models.OneToOneField(
        auth_models.User, on_delete=models.CASCADE, related_name="profile"
    )
    academy = models.ForeignKey(
        Academy, on_delete=models.SET_NULL, null=True, related_name="athletes"
    )

    role = models.CharField(
        max_length=20, choices=RoleChoices.choices, default="STUDENT"
    )
    belt = models.CharField(
        max_length=20, choices=Belt.BeltColor.choices, default="WHITE"
    )
    stripes = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} - {self.get_belt_display()} ({self.academy.name if self.academy else 'Sin Academia'})"
