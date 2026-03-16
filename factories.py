"""
Central factory_boy factories for all FlowRoll models.
Import in tests: from factories import UserFactory, AthleteProfileFactory, ...
"""
from datetime import date, timedelta
from decimal import Decimal

import factory
import factory.fuzzy
from django.contrib.auth.models import User
from django.utils import timezone
from factory.django import DjangoModelFactory


class AcademyFactory(DjangoModelFactory):
    class Meta:
        model = "academies.Academy"

    name = factory.Sequence(lambda n: f"Academy {n}")
    city = factory.Faker("city")


class BeltFactory(DjangoModelFactory):
    class Meta:
        model = "core.Belt"
        django_get_or_create = ("color",)

    color = factory.Iterator(["white", "blue", "purple", "brown", "black"])
    description = ""
    order = factory.Sequence(lambda n: n + 1)


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")
    is_active = True


class AcademyMembershipFactory(DjangoModelFactory):
    class Meta:
        model = "core.AcademyMembership"

    user = factory.SubFactory(UserFactory)
    academy = factory.SubFactory(AcademyFactory)
    role = "STUDENT"
    is_active = True


class AthleteProfileFactory(DjangoModelFactory):
    class Meta:
        model = "athletes.AthleteProfile"

    user = factory.SubFactory(UserFactory)
    academy = factory.SubFactory(AcademyFactory)
    belt = "white"
    stripes = 0
    weight = 75.0
    mat_hours = 0.0


class TechniqueCategoryFactory(DjangoModelFactory):
    class Meta:
        model = "techniques.TechniqueCategory"

    name = factory.Sequence(lambda n: f"Category {n}")


class TechniqueFactory(DjangoModelFactory):
    class Meta:
        model = "techniques.Technique"

    name = factory.Sequence(lambda n: f"Technique {n}")
    description = factory.Faker("paragraph")
    min_belt = "white"
    difficulty = 1


class TechniqueFlowFactory(DjangoModelFactory):
    class Meta:
        model = "techniques.TechniqueFlow"

    from_technique = factory.SubFactory(TechniqueFactory)
    to_technique = factory.SubFactory(TechniqueFactory)
    transition_type = "chain"


class TrainingClassFactory(DjangoModelFactory):
    class Meta:
        model = "attendance.TrainingClass"

    academy = factory.SubFactory(AcademyFactory)
    title = factory.Sequence(lambda n: f"Class {n}")
    class_type = "GI"
    professor = factory.SubFactory(UserFactory)
    scheduled_at = factory.LazyFunction(timezone.now)
    duration_minutes = 60


class QRCodeFactory(DjangoModelFactory):
    class Meta:
        model = "attendance.QRCode"

    training_class = factory.SubFactory(TrainingClassFactory)
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(minutes=30))
    is_active = True


class CheckInFactory(DjangoModelFactory):
    class Meta:
        model = "attendance.CheckIn"

    athlete = factory.SubFactory(AthleteProfileFactory)
    training_class = factory.SubFactory(TrainingClassFactory)
    method = "QR"


class DropInVisitorFactory(DjangoModelFactory):
    class Meta:
        model = "attendance.DropInVisitor"

    academy = factory.SubFactory(AcademyFactory)
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.Faker("email")
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=24))
    status = "ACTIVE"


class WeightClassFactory(DjangoModelFactory):
    class Meta:
        model = "tatami.WeightClass"

    name = factory.Sequence(lambda n: f"Weight {n}")
    min_weight = 60.0
    max_weight = 76.0
    gender = "O"


class TimerPresetFactory(DjangoModelFactory):
    class Meta:
        model = "tatami.TimerPreset"

    academy = factory.SubFactory(AcademyFactory)
    name = factory.Sequence(lambda n: f"Preset {n}")
    format = "CUSTOM"
    round_duration_seconds = 300
    rest_duration_seconds = 60
    overtime_seconds = 0
    rounds = 1


class MatchupFactory(DjangoModelFactory):
    class Meta:
        model = "tatami.Matchup"

    academy = factory.SubFactory(AcademyFactory)
    athlete_a = factory.SubFactory(AthleteProfileFactory)
    athlete_b = factory.SubFactory(AthleteProfileFactory)
    match_format = "TOURNAMENT"
    round_number = 1
    status = "PENDING"


class MembershipPlanFactory(DjangoModelFactory):
    class Meta:
        model = "membership.MembershipPlan"

    academy = factory.SubFactory(AcademyFactory)
    name = factory.Sequence(lambda n: f"Plan {n}")
    plan_type = "MONTHLY"
    price = Decimal("99.99")
    duration_days = 30
    is_active = True


class SubscriptionFactory(DjangoModelFactory):
    class Meta:
        model = "membership.Subscription"

    athlete = factory.SubFactory(AthleteProfileFactory)
    plan = factory.SubFactory(MembershipPlanFactory)
    start_date = factory.LazyFunction(date.today)
    status = "ACTIVE"


class PromotionRequirementFactory(DjangoModelFactory):
    class Meta:
        model = "membership.PromotionRequirement"

    belt = "white"
    min_mat_hours = 100.0
    min_months_at_belt = 12
    min_stripes_before_promotion = 4
    academy = None


class SeminarFactory(DjangoModelFactory):
    class Meta:
        model = "membership.Seminar"

    academy = factory.SubFactory(AcademyFactory)
    title = factory.Sequence(lambda n: f"Seminar {n}")
    instructor_name = factory.Faker("name")
    event_date = factory.LazyFunction(lambda: timezone.now() + timedelta(days=30))
    capacity = 20
    price = Decimal("50.00")
    status = "OPEN"


class SeminarRegistrationFactory(DjangoModelFactory):
    class Meta:
        model = "membership.SeminarRegistration"

    seminar = factory.SubFactory(SeminarFactory)
    athlete = factory.SubFactory(AthleteProfileFactory)
    status = "CONFIRMED"
    payment_status = "UNPAID"


class AchievementFactory(DjangoModelFactory):
    class Meta:
        model = "community.Achievement"

    name = factory.Sequence(lambda n: f"Achievement {n}")
    description = factory.Faker("sentence")
    trigger_type = "CHECKIN_COUNT"
    trigger_value = 10.0


class OpenMatSessionFactory(DjangoModelFactory):
    class Meta:
        model = "community.OpenMatSession"

    academy = factory.SubFactory(AcademyFactory)
    title = "Open Mat"
    event_date = factory.LazyFunction(lambda: date.today() + timedelta(days=7))
    start_time = "10:00:00"
    is_cancelled = False


class SparringNoteFactory(DjangoModelFactory):
    class Meta:
        model = "learning.SparringNote"

    athlete = factory.SubFactory(AthleteProfileFactory)
    session_date = factory.LazyFunction(date.today)
    opponent_name = factory.Faker("name")
    notes = factory.Faker("paragraph")
    performance_rating = 3


class VideoLibraryItemFactory(DjangoModelFactory):
    class Meta:
        model = "learning.VideoLibraryItem"

    academy = factory.SubFactory(AcademyFactory)
    title = factory.Sequence(lambda n: f"Video {n}")
    url = "https://youtube.com/watch?v=test"
    source = "YOUTUBE"
    visibility = "MEMBERS_ONLY"
