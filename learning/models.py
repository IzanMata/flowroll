from django.db import models

from core.mixins import TenantMixin, TimestampMixin


class ClassTechniqueJournal(TimestampMixin):
    """Records which techniques were drilled during a specific training class."""

    training_class = models.ForeignKey(
        "attendance.TrainingClass",
        on_delete=models.CASCADE,
        related_name="technique_journals",
    )
    technique = models.ForeignKey(
        "techniques.Technique",
        on_delete=models.CASCADE,
        related_name="journal_entries",
    )
    professor_notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("training_class", "technique")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.technique.name} @ {self.training_class}"


class VideoLibraryItem(TenantMixin, TimestampMixin):
    """A private video link stored in an academy's learning library."""

    class Source(models.TextChoices):
        YOUTUBE = "YOUTUBE", "YouTube"
        VIMEO = "VIMEO", "Vimeo"
        OTHER = "OTHER", "Other"

    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", "Public (all members)"
        PROFESSORS = "PROFESSORS", "Professors only"
        PRIVATE = "PRIVATE", "Private"

    title = models.CharField(max_length=200)
    url = models.URLField()
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.YOUTUBE
    )
    visibility = models.CharField(
        max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC
    )
    # Optional link to a specific technique this video demonstrates
    technique = models.ForeignKey(
        "techniques.Technique",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="library_videos",
    )
    belt_level = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class SparringNote(TimestampMixin):
    """Personal notes an athlete records after a sparring session."""

    class PerformanceRating(models.IntegerChoices):
        POOR = 1, "Poor"
        FAIR = 2, "Fair"
        GOOD = 3, "Good"
        GREAT = 4, "Great"
        EXCELLENT = 5, "Excellent"

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="sparring_notes",
    )
    # Optional – note can be tied to a specific class or be standalone
    training_class = models.ForeignKey(
        "attendance.TrainingClass",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sparring_notes",
    )
    opponent_name = models.CharField(max_length=100, blank=True)
    session_date = models.DateField()
    submission_log = models.TextField(
        blank=True,
        help_text="Comma-separated list of submissions attempted/achieved.",
    )
    performance_rating = models.IntegerField(
        choices=PerformanceRating.choices, null=True, blank=True
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-session_date"]

    def __str__(self):
        return f"{self.athlete} sparring note {self.session_date}"
