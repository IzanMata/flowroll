from decimal import Decimal

from django.db import models

from core.mixins import TenantMixin, TimestampMixin


class MembershipPlan(TenantMixin, TimestampMixin):
    """A membership plan offered by an academy (monthly, annual, class-pass, etc.)."""

    class PlanType(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        ANNUAL = "ANNUAL", "Annual"
        CLASS_PASS = "CLASS_PASS", "Class Pass"
        DROP_IN = "DROP_IN", "Drop-In"

    name = models.CharField(max_length=100)
    plan_type = models.CharField(max_length=20, choices=PlanType.choices)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    # Number of days the plan is valid. None means open-ended (e.g. monthly billing).
    duration_days = models.PositiveIntegerField(null=True, blank=True)
    # Max classes per plan period. None means unlimited.
    class_limit = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.academy})"


class Subscription(TimestampMixin):
    """An athlete's active (or historical) subscription to a MembershipPlan."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        CANCELLED = "CANCELLED", "Cancelled"
        PAUSED = "PAUSED", "Paused"

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT, related_name="subscriptions")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    classes_remaining = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["athlete", "status"]),
        ]

    def __str__(self):
        return f"{self.athlete} – {self.plan.name} ({self.status})"


class PromotionRequirement(models.Model):
    """
    Minimum criteria an athlete must meet before a belt promotion.

    academy is optional (null = global default). When both a global and an
    academy-specific requirement exist for the same belt, the academy-specific
    one wins (see PromotionService._get_requirement).
    """

    academy = models.ForeignKey(
        "academies.Academy",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="promotion_requirements",
    )
    belt = models.CharField(max_length=20)
    min_mat_hours = models.FloatField(default=0.0)
    min_months_at_belt = models.PositiveIntegerField(default=0)
    min_stripes_before_promotion = models.PositiveIntegerField(default=4)

    class Meta:
        unique_together = ("academy", "belt")

    def __str__(self):
        scope = str(self.academy) if self.academy_id else "global"
        return f"{self.belt} requirements ({scope})"


class DojoTabTransaction(TenantMixin, TimestampMixin):
    """A single debit or credit entry on an athlete's dojo tab."""

    class TransactionType(models.TextChoices):
        DEBIT = "DEBIT", "Debit"
        CREDIT = "CREDIT", "Credit"

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="tab_transactions",
    )
    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    billed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.transaction_type} {self.amount} – {self.athlete}"


class DojoTabBalance(TenantMixin):
    """Running balance on an athlete's dojo tab per academy."""

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="tab_balances",
    )
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        unique_together = ("athlete", "academy")

    def __str__(self):
        return f"{self.athlete} balance: {self.balance}"


class Seminar(TenantMixin, TimestampMixin):
    """A special event or seminar hosted by an academy."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        FULL = "FULL", "Full"
        CANCELLED = "CANCELLED", "Cancelled"
        COMPLETED = "COMPLETED", "Completed"

    title = models.CharField(max_length=200)
    instructor_name = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    event_date = models.DateField()
    capacity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["event_date"]

    @property
    def spots_remaining(self) -> int:
        confirmed = self.registrations.filter(
            status=SeminarRegistration.RegistrationStatus.CONFIRMED
        ).count()
        return max(0, self.capacity - confirmed)

    def __str__(self):
        return f"{self.title} ({self.event_date})"


class SeminarRegistration(TimestampMixin):
    """An athlete's registration for a seminar."""

    class RegistrationStatus(models.TextChoices):
        CONFIRMED = "CONFIRMED", "Confirmed"
        WAITLISTED = "WAITLISTED", "Waitlisted"
        CANCELLED = "CANCELLED", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        REFUNDED = "REFUNDED", "Refunded"

    seminar = models.ForeignKey(Seminar, on_delete=models.CASCADE, related_name="registrations")
    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="seminar_registrations",
    )
    status = models.CharField(
        max_length=20, choices=RegistrationStatus.choices, default=RegistrationStatus.CONFIRMED
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("seminar", "athlete")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.athlete} – {self.seminar.title} ({self.status})"
