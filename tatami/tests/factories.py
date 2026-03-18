import factory
from factory.django import DjangoModelFactory
import random

from tatami.models import WeightClass, TimerPreset, TimerSession, Matchup
from academies.tests.factories import AcademyFactory
from athletes.tests.factories import AthleteProfileFactory
from core.tests.factories import UserFactory


class WeightClassFactory(DjangoModelFactory):
    class Meta:
        model = WeightClass

    name = factory.Iterator([
        "Rooster", "Light-Feather", "Feather", "Light", "Middle",
        "Medium-Heavy", "Heavy", "Super-Heavy", "Ultra-Heavy"
    ])
    gender = factory.LazyAttribute(lambda obj: random.choice([
        WeightClass.Gender.MALE, WeightClass.Gender.FEMALE, WeightClass.Gender.OPEN
    ]))

    @factory.lazy_attribute
    def min_weight(self):
        weight_ranges = {
            "Rooster": (57, 64), "Light-Feather": (64, 70), "Feather": (70, 76),
            "Light": (76, 82), "Middle": (82, 88), "Medium-Heavy": (88, 94),
            "Heavy": (94, 100), "Super-Heavy": (100, 110), "Ultra-Heavy": (110, 120)
        }
        return weight_ranges.get(self.name, (70, 80))[0]

    @factory.lazy_attribute
    def max_weight(self):
        weight_ranges = {
            "Rooster": (57, 64), "Light-Feather": (64, 70), "Feather": (70, 76),
            "Light": (76, 82), "Middle": (82, 88), "Medium-Heavy": (88, 94),
            "Heavy": (94, 100), "Super-Heavy": (100, 110), "Ultra-Heavy": (110, 120)
        }
        return weight_ranges.get(self.name, (70, 80))[1]


class TimerPresetFactory(DjangoModelFactory):
    class Meta:
        model = TimerPreset

    academy = factory.SubFactory(AcademyFactory)
    name = factory.LazyAttribute(
        lambda obj: random.choice(["IBJJF Tournament", "ADCC Rules", "Positional Sparring"])
    )
    format = factory.LazyAttribute(
        lambda obj: random.choice([
            TimerPreset.Format.IBJJF,
            TimerPreset.Format.ADCC,
            TimerPreset.Format.POSITIONAL,
            TimerPreset.Format.CUSTOM
        ])
    )
    round_duration_seconds = factory.LazyAttribute(
        lambda obj: {
            TimerPreset.Format.IBJJF: 300,
            TimerPreset.Format.ADCC: 600,
            TimerPreset.Format.POSITIONAL: 180,
            TimerPreset.Format.CUSTOM: 420
        }.get(obj.format, 300)
    )
    rest_duration_seconds = factory.LazyAttribute(lambda obj: random.choice([30, 60, 90]))
    overtime_seconds = factory.LazyAttribute(lambda obj: random.choice([0, 60, 120]))
    rounds = factory.LazyAttribute(lambda obj: random.randint(1, 3))


class TimerSessionFactory(DjangoModelFactory):
    class Meta:
        model = TimerSession

    preset = factory.SubFactory(TimerPresetFactory)
    status = factory.LazyAttribute(
        lambda obj: random.choice([
            TimerSession.Status.IDLE,
            TimerSession.Status.RUNNING,
            TimerSession.Status.PAUSED,
            TimerSession.Status.FINISHED
        ])
    )
    current_round = 1
    elapsed_seconds = 0


class MatchupFactory(DjangoModelFactory):
    class Meta:
        model = Matchup

    academy = factory.SubFactory(AcademyFactory)
    athlete_a = factory.SubFactory(AthleteProfileFactory)
    athlete_b = factory.SubFactory(AthleteProfileFactory)
    weight_class = factory.SubFactory(WeightClassFactory)
    match_format = factory.LazyAttribute(
        lambda obj: random.choice([
            Matchup.MatchFormat.TOURNAMENT,
            Matchup.MatchFormat.SURVIVAL
        ])
    )
    round_number = factory.LazyAttribute(lambda obj: random.randint(1, 3))
    status = factory.LazyAttribute(
        lambda obj: random.choice([
            Matchup.Status.PENDING,
            Matchup.Status.IN_PROGRESS,
            Matchup.Status.COMPLETED,
            Matchup.Status.CANCELLED
        ])
    )
    winner = factory.LazyAttribute(
        lambda obj: random.choice([obj.athlete_a, obj.athlete_b, None])
        if obj.status == Matchup.Status.COMPLETED else None
    )