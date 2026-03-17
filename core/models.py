from django.contrib.auth.models import User
from django.db import models


class Belt(models.Model):
    """
    Reference data for BJJ belt colours in progression order.

    Used as a vocabulary table for AthleteProfile.belt (CharField with choices)
    and for promotion-requirement lookups. Managed via data migrations and the
    Django admin — not writable through the API (BeltViewSet is read-only).
    """

    class BeltColor(models.TextChoices):
        WHITE = "white", "White"
        BLUE = "blue", "Blue"
        PURPLE = "purple", "Purple"
        BROWN = "brown", "Brown"
        BLACK = "black", "Black"

    color = models.CharField(max_length=20, choices=BeltColor.choices, unique=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(
        help_text="Belt progression order: 1=white … 5=black"
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.get_color_display()


class AcademyMembership(models.Model):
    """
    Represents a user's role within a specific academy.
    Enables row-level multi-tenancy: every user can belong to multiple
    academies with different roles.
    """

    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        PROFESSOR = "PROFESSOR", "Professor"
        OWNER = "OWNER", "Owner"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="academy_memberships",
    )
    academy = models.ForeignKey(
        "academies.Academy",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "academy")
        indexes = [
            models.Index(fields=["user", "academy", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user.username} @ {self.academy} ({self.role})"
