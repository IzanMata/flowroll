from django.db import models
from django.utils import timezone


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

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Technique(models.Model):
    name = models.CharField(max_length=200)
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
    video_url = models.URLField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("name",)

    def __str__(self):
        return self.name


class TechniqueFlow(models.Model):
    from_technique = models.ForeignKey(
        Technique, on_delete=models.CASCADE, related_name="leads_to"
    )
    to_technique = models.ForeignKey(
        Technique, on_delete=models.CASCADE, related_name="comes_from"
    )
    description = models.TextField(blank=True)
    probability = models.FloatField(default=1.0)

    class Meta:
        unique_together = ("from_technique", "to_technique")


class TechniqueVariation(models.Model):
    technique = models.ForeignKey(
        Technique, on_delete=models.CASCADE, related_name="variations"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ("technique", "name")

    def __str__(self):
        return f"{self.technique.name} → {self.name}"
