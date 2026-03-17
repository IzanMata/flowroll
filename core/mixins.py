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


# ViewSet Mixins for eliminating common duplication patterns


class SwaggerSafeMixin:
    """
    ViewSet mixin to handle swagger_fake_view gracefully.
    Eliminates duplication of the same check across multiple ViewSets.

    Usage: Inherit this mixin in your ViewSet and call super().get_queryset() first.
    """

    def get_queryset(self):
        """Override this in your ViewSet and call super() first."""
        if getattr(self, "swagger_fake_view", False):
            # Return empty queryset for Swagger documentation generation
            return self.queryset.model.objects.none()

        # Let the actual ViewSet handle the real queryset logic
        return super().get_queryset()


class AcademyFilterMixin:
    """
    ViewSet mixin to handle academy-scoped querysets consistently.
    Eliminates duplication of academy parameter extraction and validation.
    """

    def get_academy_id(self):
        """Extract academy ID from URL kwargs or query params."""
        return self.kwargs.get("academy_pk") or self.request.query_params.get("academy")

    def filter_by_academy(self, queryset):
        """Filter queryset by academy, returning empty if academy not found."""
        academy_id = self.get_academy_id()
        if not academy_id:
            return queryset.none()

        return queryset.filter(academy_id=academy_id)

    def get_academy_scoped_queryset(self, queryset):
        """
        Get queryset scoped to academy with membership validation.
        Returns empty queryset if user is not an active academy member.
        """
        from core.permissions import get_academy_scoped_queryset

        academy_id = self.get_academy_id()
        return get_academy_scoped_queryset(queryset, self.request.user, academy_id)
