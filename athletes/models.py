from django.contrib.auth import models as auth_models
from django.db import models

from academies.models import Academy
from core.models import Belt


class AthleteProfile(models.Model):
    """
    Extended profile for a BJJ practitioner, linked one-to-one with Django's User.

    Stores competition-relevant data (belt, stripes, weight), cumulative training
    metrics (mat_hours), and the coach lineage pointer used for ancestry-tree
    rendering. mat_hours is maintained atomically by CheckInService via F()
    expressions — never set it directly in application code.
    """

    class RoleChoices(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        PROFESSOR = "PROFESSOR", "Professor"

    user = models.OneToOneField(
        auth_models.User, on_delete=models.CASCADE, related_name="profile"
    )
    academy = models.ForeignKey(
        Academy, on_delete=models.SET_NULL, null=True, related_name="athletes"
    )
    # Martial lineage — recursive self-reference
    coach = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
        help_text="Direct instructor; enables ancestry-tree traversal.",
    )
    role = models.CharField(
        max_length=20, choices=RoleChoices.choices, default=RoleChoices.STUDENT
    )
    belt = models.CharField(
        max_length=20, choices=Belt.BeltColor.choices, default=Belt.BeltColor.WHITE
    )
    stripes = models.IntegerField(default=0)
    weight = models.FloatField(
        null=True,
        blank=True,
        help_text="Body weight in kilograms, used for matchmaking.",
    )
    mat_hours = models.FloatField(
        default=0.0,
        help_text="Cumulative mat hours derived from attendance check-ins.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["academy", "belt"]),
        ]

    def __str__(self):
        return (
            f"{self.user.username} — {self.get_belt_display()} "
            f"({self.academy.name if self.academy else 'No Academy'})"
        )

    def get_lineage(self) -> list:
        """Return the ancestry chain from this athlete up to the root instructor.

        M-9 fix: track visited nodes to break out of circular coach references
        (e.g. A.coach=B, B.coach=A) that would otherwise loop forever.
        """
        chain = []
        visited_ids: set = set()
        current = self.coach
        while current is not None and current.pk not in visited_ids:
            visited_ids.add(current.pk)
            chain.append(current)
            current = current.coach
        return chain
