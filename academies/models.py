from django.db import models


class Academy(models.Model):
    """
    The tenant root for the FlowRoll multi-tenancy model.

    Every tenant-scoped model carries an FK to Academy via TenantMixin.
    Users gain access to an academy's data through AcademyMembership records
    (in core.models), which also carry the user's role (STUDENT, PROFESSOR, OWNER).
    """

    name = models.CharField(max_length=150)
    city = models.CharField(max_length=100, blank=True)
    # TODO Aquí en el futuro puedes añadir 'logo', 'stripe_account_id' (para cobros), etc.
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
