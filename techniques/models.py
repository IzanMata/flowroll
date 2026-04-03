from django.db import models
from django.utils.text import slugify

from core.mixins import TimestampMixin
from core.models import Belt


class AutoSlugMixin(models.Model):
    """Abstract mixin: auto-populates `slug` from `name` on first save."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class TechniqueCategory(AutoSlugMixin, models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True, null=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Technique(AutoSlugMixin, TimestampMixin, models.Model):

    class DifficultyLevel(models.IntegerChoices):
        ONE = 1, "1 Star"
        TWO = 2, "2 Stars"
        THREE = 3, "3 Stars"
        FOUR = 4, "4 Stars"
        FIVE = 5, "5 Stars"

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    categories = models.ManyToManyField("TechniqueCategory", related_name="techniques")
    description = models.TextField(blank=True)
    difficulty = models.PositiveSmallIntegerField(
        choices=DifficultyLevel.choices,
        default=DifficultyLevel.ONE,
    )
    min_belt = models.CharField(
        max_length=10,
        choices=Belt.BeltColor.choices,
        default=Belt.BeltColor.WHITE,
    )
    image_url = models.URLField(blank=True)
    source_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Source of the data, e.g., 'BlackBeltWiki'",
    )
    source_url = models.URLField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TechniqueVideo(TimestampMixin, models.Model):
    technique = models.ForeignKey(
        Technique, on_delete=models.CASCADE, related_name="videos"
    )
    title = models.CharField(max_length=200, blank=True)
    url = models.URLField(blank=True)
    source = models.CharField(max_length=100, default="YouTube")
    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Video duration in seconds.",
    )
    tags = models.CharField(
        max_length=500,
        blank=True,
        help_text="Comma-separated keywords for search (e.g. 'guard,sweep,gi').",
    )

    class Meta:
        ordering = ["technique", "id"]

    def __str__(self):
        return f"{self.technique.name} - {self.title or 'Video'}"


class TechniqueVariation(models.Model):
    technique = models.ForeignKey(
        Technique, on_delete=models.CASCADE, related_name="variations"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    videos = models.ManyToManyField(
        TechniqueVideo, blank=True, related_name="variations"
    )

    class Meta:
        unique_together = ("technique", "name")

    def __str__(self):
        return f"{self.technique.name} → {self.name}"


class TechniqueFlow(models.Model):

    class TransitionTypes(models.TextChoices):
        CHAIN = "chain", "Chain"
        COUNTER = "counter", "Counter"
        ESCAPE = "escape", "Escape"
        SETUP = "setup", "Setup"

    from_technique = models.ForeignKey(
        Technique, on_delete=models.CASCADE, related_name="leads_to"
    )
    to_technique = models.ForeignKey(
        Technique, on_delete=models.CASCADE, related_name="comes_from"
    )
    transition_type = models.CharField(
        max_length=20, choices=TransitionTypes.choices, default="chain"
    )
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ("from_technique", "to_technique")

    def __str__(self):
        return f"{self.from_technique} → {self.to_technique} ({self.get_transition_type_display()})"
