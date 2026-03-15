from django.contrib.auth import models as auth_models
from django.db import models


class Match(models.Model):
    athlete_a = models.ForeignKey(
        auth_models.User, on_delete=models.CASCADE, related_name="matches_a"
    )
    athlete_b = models.ForeignKey(
        auth_models.User, on_delete=models.CASCADE, related_name="matches_b"
    )
    date = models.DateTimeField(auto_now_add=True)
    duration_seconds = models.IntegerField(default=300)
    is_finished = models.BooleanField(default=False)

    score_a = models.IntegerField(default=0)
    score_b = models.IntegerField(default=0)
    winner = models.ForeignKey(
        auth_models.User, on_delete=models.SET_NULL, null=True, blank=True
    )


class MatchEvent(models.Model):
    TYPE_CHOICES = [
        ("POINTS", "Points"),
        ("ADVANTAGE", "Advantage"),
        ("PENALTY", "Penalty"),
        ("SUBMISSION", "Submission"),
    ]

    match = models.ForeignKey(Match, related_name="events", on_delete=models.CASCADE)
    athlete = models.ForeignKey(auth_models.User, on_delete=models.CASCADE)
    timestamp = models.IntegerField()
    points_awarded = models.IntegerField(default=0)
    action_description = models.CharField(max_length=100)
    event_type = models.CharField(max_length=15, choices=TYPE_CHOICES)
