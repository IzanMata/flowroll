from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from core.models import Belt


# TODO:
# slug podría ser obligatorio para URLs amigables.
class TechniqueCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True, null=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# TODO
# difficulty podría ser un PositiveSmallIntegerField con choices (1-5 estrellas, por ejemplo).
# Considerar agregar:
# type o category directo aquí para filtrar técnicas sin JOIN con techniques_technique_categories.
# gi_allowed y no_gi_allowed booleanos si quieres filtrar según modalidad.
# Si quieres soporte internacional, añadir campos name_en, description_en para traducciones.


class Technique(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    categories = models.ManyToManyField("TechniqueCategory", related_name="techniques")
    description = models.TextField(blank=True)
    difficulty = models.IntegerField(default=1)
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


# TODO
# Añadir un campo duration (segundos o minutos).
# Campo tags o keywords para búsqueda avanzada.
class TechniqueVideo(models.Model):
    technique = models.ForeignKey(
        Technique, on_delete=models.CASCADE, related_name="videos"
    )
    title = models.CharField(max_length=200, blank=True)
    url = models.URLField(blank=True)
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
