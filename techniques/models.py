from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Belt(models.Model):
    COLOR_CHOICES = [
        ("white", "White"),
        ("blue", "Blue"),
        ("purple", "Purple"),
        ("brown", "Brown"),
        ("black", "Black"),
    ]

    color = models.CharField(max_length=20, choices=COLOR_CHOICES, unique=True)
    order = models.PositiveIntegerField(
        help_text="Orden de progresión del cinturón, 1=white, 5=black"
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.get_color_display()


class TechniqueCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Technique(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    categories = models.ManyToManyField("TechniqueCategory", related_name="techniques")
    description = models.TextField(blank=True)
    difficulty = models.IntegerField(default=1)
    min_belt = models.ForeignKey(
        "Belt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="techniques",
    )
    image_url = models.URLField(blank=True)
    source_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Origen del dato, por ejemplo 'BlackBeltWiki'",
    )
    source_url = models.URLField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class TechniqueVideo(models.Model):
    technique = models.ForeignKey(
        Technique, on_delete=models.CASCADE, related_name="videos"
    )
    title = models.CharField(max_length=200, blank=True)
    url = models.URLField()
    source = models.CharField(max_length=100, default="YouTube")
    created_at = models.DateTimeField(default=timezone.now)

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
    TRANSITION_TYPES = [
        ("chain", "Encadenamiento"),
        ("counter", "Contraataque"),
        ("escape", "Escape"),
        ("setup", "Preparación"),
    ]

    from_technique = models.ForeignKey(
        Technique, on_delete=models.CASCADE, related_name="leads_to"
    )
    to_technique = models.ForeignKey(
        Technique, on_delete=models.CASCADE, related_name="comes_from"
    )
    transition_type = models.CharField(
        max_length=20, choices=TRANSITION_TYPES, default="chain"
    )
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ("from_technique", "to_technique")

    def __str__(self):
        return f"{self.from_technique} → {self.to_technique} ({self.get_transition_type_display()})"
