import factory
from factory.django import DjangoModelFactory
import random
from datetime import timedelta
from django.utils import timezone

from matches.models import Match, MatchEvent
from core.tests.factories import UserFactory


class MatchFactory(DjangoModelFactory):
    class Meta:
        model = Match

    athlete_a = factory.SubFactory(UserFactory)
    athlete_b = factory.SubFactory(UserFactory)
    duration_seconds = factory.LazyAttribute(lambda obj: random.randint(300, 600))  # 5-10 min


class MatchEventFactory(DjangoModelFactory):
    class Meta:
        model = MatchEvent

    match = factory.SubFactory(MatchFactory)
    athlete = factory.LazyAttribute(lambda obj: random.choice([obj.match.athlete_a, obj.match.athlete_b]))
    timestamp = factory.LazyAttribute(lambda obj: random.randint(0, obj.match.duration_seconds))
    event_type = factory.LazyAttribute(
        lambda obj: random.choice([
            MatchEvent.TypeChoices.POINTS,
            MatchEvent.TypeChoices.ADVANTAGE,
            MatchEvent.TypeChoices.PENALTY,
            MatchEvent.TypeChoices.SUBMISSION
        ])
    )
    points_awarded = factory.LazyAttribute(
        lambda obj: random.choice([1, 2, 3, 4]) if obj.event_type == MatchEvent.TypeChoices.POINTS else 0
    )
    action_description = factory.LazyAttribute(
        lambda obj: random.choice([
            "Takedown", "Sweep", "Guard Pass", "Mount", "Back Control",
            "Knee on Belly", "Advantage", "Penalty", "Submission Attempt"
        ])
    )