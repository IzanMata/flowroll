from django.db import models

from core.mixins import TimestampMixin


class Academy(TimestampMixin):
    """
    The tenant root for the FlowRoll multi-tenancy model.

    Every tenant-scoped model carries an FK to Academy via TenantMixin.
    Users gain access to an academy's data through AcademyMembership records
    (in core.models), which also carry the user's role (STUDENT, PROFESSOR, OWNER).
    """

    name = models.CharField(max_length=150)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active"]),
        ]
        verbose_name = "Academy"
        verbose_name_plural = "Academies"

    def __str__(self):
        if self.city:
            return f"{self.name} ({self.city})"
        return self.name
