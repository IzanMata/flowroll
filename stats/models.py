"""
Materialized statistics models for athlete and academy performance.

AthleteMatchStats caches match-derived stats (wins, losses, points) so
that dashboard queries do not have to scan the matches table on every
request. StatsService.recompute_for_athlete() keeps it in sync whenever
a match is finished.
"""

from django.db import models

from core.mixins import TimestampMixin


class AthleteMatchStats(TimestampMixin, models.Model):
    """
    Aggregated match statistics for a single athlete.

    Updated by StatsService whenever a match is finished. The updated_at
    timestamp (from TimestampMixin) tells consumers how fresh the data is.
    """

    athlete = models.OneToOneField(
        "athletes.AthleteProfile",
        on_delete=models.CASCADE,
        related_name="match_stats",
    )
    total_matches = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    # A match is a draw when is_finished=True but winner is NULL
    draws = models.PositiveIntegerField(default=0)
    # Sum of all POINTS events where this athlete was the scorer
    total_points_scored = models.PositiveIntegerField(default=0)
    # Sum of points scored by opponents against this athlete
    total_points_conceded = models.PositiveIntegerField(default=0)
    # Number of matches won via SUBMISSION event
    submissions_won = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Athlete Match Stats"
        verbose_name_plural = "Athlete Match Stats"

    def __str__(self):
        return (
            f"{self.athlete} — {self.wins}W / {self.losses}L / {self.draws}D"
        )

    @property
    def win_rate(self) -> float:
        """Win percentage (0.0–1.0). Returns 0.0 if no matches played."""
        if self.total_matches == 0:
            return 0.0
        return self.wins / self.total_matches
