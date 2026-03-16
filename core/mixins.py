from django.db import models


class TimestampMixin(models.Model):
    """Abstract mixin that adds created_at and updated_at fields."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantMixin(models.Model):
    """Abstract mixin that ties a model to a specific academy (tenant)."""

    academy = models.ForeignKey(
        "academies.Academy",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    class Meta:
        abstract = True
