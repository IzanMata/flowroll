from django.db import models

from core.mixins import TenantMixin, TimestampMixin


class Achievement(models.Model):
    """
    Platform-wide badge definition.
    Examples: "First Check-In", "50 Mat Hours", "30-Day Streak".
    """

    class TriggerType(models.TextChoices):
        CHECKIN_COUNT = "CHECKIN_COUNT", "Total check-ins"
        MAT_HOURS = "MAT_HOURS", "Cumulative mat hours"
        STREAK_DAYS = "STREAK_DAYS", "Consecutive training days"
        MANUAL = "MANUAL", "Manually awarded by professor"

    name = models.CharField(max_length=80, unique=True)
    description = models.TextField()
    icon_url = models.URLField(blank=True)
    trigger_type = models.CharField(max_length=20, choices=TriggerType.choices)
    trigger_value = models.FloatField(
        null=True,
        blank=True,
        help_text="Numeric threshold at which this achievement is automatically awarded.",
    )

    def __str__(self):
        return self.name


class AthleteAchievement(TimestampMixin):
    """Records that an athlete has earned a specific Achievement."""

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="achievements",
    )
    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name="athlete_achievements",
    )
    awarded_by = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="achievements_awarded",
        help_text="Professor who manually awarded this badge.",
    )

    class Meta:
        unique_together = ("athlete", "achievement")

    def __str__(self):
        return f"{self.athlete} earned {self.achievement}"


class OpenMatSession(TenantMixin, TimestampMixin):
    """
    An open / informal training event that athletes can RSVP to.
    Typically used for weekend rolls.
    """

    title = models.CharField(max_length=120, default="Open Mat")
    event_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField(null=True, blank=True)
    max_capacity = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    is_cancelled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-event_date"]
        indexes = [models.Index(fields=["academy", "event_date"])]

    def __str__(self):
        return f"{self.title} @ {self.academy} on {self.event_date}"

    @property
    def going_count(self) -> int:
        return self.rsvps.filter(status=OpenMatRSVP.Status.GOING).count()


class OpenMatRSVP(TimestampMixin):
    """An athlete's intention-to-attend declaration for an OpenMatSession."""

    class Status(models.TextChoices):
        GOING = "GOING", "Going"
        NOT_GOING = "NOT_GOING", "Not Going"
        MAYBE = "MAYBE", "Maybe"

    session = models.ForeignKey(
        OpenMatSession,
        on_delete=models.CASCADE,
        related_name="rsvps",
    )
    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="open_mat_rsvps",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.GOING
    )

    class Meta:
        unique_together = ("session", "athlete")
        indexes = [
            # P8 fix: going_count annotation filters rsvps by (session, status)
            models.Index(
                fields=["session", "status"], name="openmatrsvp_session_status_idx"
            ),
        ]

    def __str__(self):
        return f"{self.athlete} → {self.session} ({self.status})"
