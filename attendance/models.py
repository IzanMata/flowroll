import secrets
import uuid
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from core.mixins import TimestampMixin, TenantMixin


class TrainingClass(TenantMixin, TimestampMixin):
    """A scheduled training session at an academy."""

    class ClassType(models.TextChoices):
        GI = "GI", "Gi"
        NOGI = "NOGI", "No-Gi"
        OPEN_MAT = "OPEN_MAT", "Open Mat"
        KIDS = "KIDS", "Kids"
        COMPETITION = "COMPETITION", "Competition Prep"

    title = models.CharField(max_length=120)
    class_type = models.CharField(max_length=20, choices=ClassType.choices, default=ClassType.GI)
    professor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="classes_taught",
    )
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=60)
    max_capacity = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-scheduled_at"]
        indexes = [
            models.Index(fields=["academy", "scheduled_at"]),
        ]

    def __str__(self):
        return f"{self.title} — {self.scheduled_at:%Y-%m-%d %H:%M}"


class QRCode(TimestampMixin):
    """
    A time-limited QR code token tied to a TrainingClass.
    Athletes scan this to check in.
    """

    training_class = models.OneToOneField(
        TrainingClass,
        on_delete=models.CASCADE,
        related_name="qr_code",
    )
    token = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["token", "is_active"])]

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    @property
    def is_valid(self) -> bool:
        return self.is_active and timezone.now() < self.expires_at

    def __str__(self):
        return f"QR:{self.token[:8]}… ({self.training_class})"


class CheckIn(TimestampMixin):
    """Records an athlete's attendance at a TrainingClass."""

    class Method(models.TextChoices):
        QR = "QR", "QR Scan"
        MANUAL = "MANUAL", "Manual"

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="check_ins",
    )
    training_class = models.ForeignKey(
        TrainingClass,
        on_delete=models.CASCADE,
        related_name="check_ins",
    )
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.QR)
    checked_in_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("athlete", "training_class")
        indexes = [models.Index(fields=["athlete", "training_class"])]

    def __str__(self):
        return f"{self.athlete} @ {self.training_class}"


class DropInVisitor(TimestampMixin):
    """Temporary visitor with a one-time access token for drop-in sessions."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"

    academy = models.ForeignKey(
        "academies.Academy",
        on_delete=models.CASCADE,
        related_name="drop_in_visitors",
    )
    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    training_class = models.ForeignKey(
        TrainingClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drop_in_visitors",
    )
    access_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    class Meta:
        indexes = [models.Index(fields=["academy", "status"])]

    def __str__(self):
        return f"{self.first_name} {self.last_name} (drop-in @ {self.academy})"
