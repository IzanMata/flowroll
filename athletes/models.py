from django.contrib.auth import models as auth_models
from django.db import models

from academies.models import Academy


class AthleteProfile(models.Model):
    ROLE_CHOICES = [
        ("STUDENT", "Student"),
        ("PROFESSOR", "Professor"),
    ]

    BELT_CHOICES = [
        ("WHITE", "Blanco"),
        ("BLUE", "Azul"),
        ("PURPLE", "Morado"),
        ("BROWN", "Marrón"),
        ("BLACK", "Negro"),
    ]

    user = models.OneToOneField(
        auth_models.User, on_delete=models.CASCADE, related_name="profile"
    )
    academy = models.ForeignKey(
        Academy, on_delete=models.SET_NULL, null=True, related_name="athletes"
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="STUDENT")
    belt = models.CharField(max_length=20, choices=BELT_CHOICES, default="WHITE")
    stripes = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} - {self.get_belt_display()} ({self.academy.name if self.academy else 'Sin Academia'})"
