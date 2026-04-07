"""
Central factory_boy factories for all FlowRoll models.
Import in tests: from factories import UserFactory, AthleteProfileFactory, ...
"""

import random
from datetime import date, timedelta
from decimal import Decimal

import factory
import factory.fuzzy
from django.contrib.auth.models import User
from django.utils import timezone
from factory.django import DjangoModelFactory
from faker import Faker

fake = Faker()


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
        skip_postgeneration_save = True

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
    belt = factory.fuzzy.FuzzyChoice(["white", "blue", "purple", "brown", "black"])
    stripes = factory.fuzzy.FuzzyInteger(0, 4)
    weight = factory.fuzzy.FuzzyFloat(55.0, 120.0)
    mat_hours = factory.fuzzy.FuzzyFloat(0.0, 1000.0)
    role = factory.fuzzy.FuzzyChoice(["STUDENT", "PROFESSOR"])
    # coach can be null - will be set by post_generation if needed


class TechniqueCategoryFactory(DjangoModelFactory):
    class Meta:
        model = "techniques.TechniqueCategory"

    name = factory.Sequence(lambda n: f"Category {n}")


class TechniqueFactory(DjangoModelFactory):
    class Meta:
        model = "techniques.Technique"
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"Technique {n}")
    description = factory.Faker("paragraph")
    min_belt = factory.fuzzy.FuzzyChoice(["white", "blue", "purple", "brown", "black"])
    difficulty = factory.fuzzy.FuzzyInteger(1, 5)
    image_url = factory.LazyFunction(lambda: f"https://via.placeholder.com/300x200?text={fake.word()}")
    source_name = factory.Faker("company")
    source_url = factory.Faker("url")

    @factory.post_generation
    def categories(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            # A list of categories were passed in, use them
            for category in extracted:
                self.categories.add(category)
        else:
            # Create 1-3 random categories for this technique
            category_count = random.randint(1, 3)
            for _ in range(category_count):
                category = TechniqueCategoryFactory()
                self.categories.add(category)


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
    phone = factory.Faker("numerify", text="+1##########")
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=24))
    status = factory.fuzzy.FuzzyChoice(["PENDING", "ACTIVE", "EXPIRED"])


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
    stripe_product_id = ""
    stripe_price_id = ""


class SubscriptionFactory(DjangoModelFactory):
    class Meta:
        model = "membership.Subscription"

    athlete = factory.SubFactory(AthleteProfileFactory)
    plan = factory.SubFactory(MembershipPlanFactory)
    start_date = factory.LazyFunction(date.today)
    status = "ACTIVE"
    stripe_subscription_id = ""


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
    payment_status = "PENDING"
    stripe_payment_intent_id = ""


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
    title = factory.LazyFunction(lambda: f"{fake.day_of_week()} Open Mat")
    event_date = factory.LazyFunction(lambda: fake.date_between(start_date="today", end_date="+30d"))
    start_time = factory.fuzzy.FuzzyChoice(["09:00:00", "10:00:00", "14:00:00", "15:00:00"])
    end_time = factory.LazyAttribute(lambda o: f"{int(o.start_time[:2]) + 2}:00:00")  # 2 hours later
    max_capacity = factory.fuzzy.FuzzyInteger(15, 35)
    description = factory.Faker("sentence")
    is_cancelled = False  # 5% chance


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
    title = factory.LazyFunction(lambda: f"BJJ Tutorial: {fake.catch_phrase()}")
    url = factory.LazyFunction(lambda: f"https://youtube.com/watch?v={fake.lexify('??????????')}")
    source = factory.fuzzy.FuzzyChoice(["YOUTUBE", "VIMEO", "OTHER"])
    visibility = factory.fuzzy.FuzzyChoice(["PUBLIC", "PROFESSORS", "PRIVATE"])
    technique = factory.SubFactory(TechniqueFactory)  # Optional reference
    belt_level = factory.fuzzy.FuzzyChoice(["white", "blue", "purple", "brown", "black"])
    description = factory.Faker("paragraph")


# ===== MISSING FACTORIES =====


class TechniqueVideoFactory(DjangoModelFactory):
    class Meta:
        model = "techniques.TechniqueVideo"

    technique = factory.SubFactory(TechniqueFactory)
    title = factory.LazyAttribute(lambda o: f"{o.technique.name} - {fake.catch_phrase()}")
    url = factory.LazyFunction(lambda: f"https://youtube.com/watch?v={fake.lexify('??????????')}")
    source = "YOUTUBE"


class TechniqueVariationFactory(DjangoModelFactory):
    class Meta:
        model = "techniques.TechniqueVariation"

    technique = factory.SubFactory(TechniqueFactory)
    name = factory.LazyAttribute(lambda o: f"{o.technique.name} Variation")
    description = factory.Faker("paragraph")

    @factory.post_generation
    def videos(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            # A list of videos were passed in, use them
            for video in extracted:
                self.videos.add(video)
        else:
            # Create 1-3 random videos for this variation
            video_count = random.randint(1, 3)
            for _ in range(video_count):
                video = TechniqueVideoFactory(technique=self.technique)
                self.videos.add(video)


class ClassTechniqueJournalFactory(DjangoModelFactory):
    class Meta:
        model = "learning.ClassTechniqueJournal"

    training_class = factory.SubFactory(TrainingClassFactory)
    technique = factory.SubFactory(TechniqueFactory)
    professor_notes = factory.LazyFunction(lambda: fake.sentence() if random.random() < 0.4 else "")


class TimerSessionFactory(DjangoModelFactory):
    class Meta:
        model = "tatami.TimerSession"

    preset = factory.SubFactory(TimerPresetFactory)
    status = factory.fuzzy.FuzzyChoice(["IDLE", "RUNNING", "PAUSED", "FINISHED"])
    current_round = factory.fuzzy.FuzzyInteger(1, 3)
    started_at = factory.LazyFunction(timezone.now)
    elapsed_seconds = factory.fuzzy.FuzzyInteger(0, 300)


class DojoTabTransactionFactory(DjangoModelFactory):
    class Meta:
        model = "membership.DojoTabTransaction"

    academy = factory.SubFactory(AcademyFactory)
    athlete = factory.SubFactory(AthleteProfileFactory)
    transaction_type = factory.fuzzy.FuzzyChoice(["DEBIT", "CREDIT"])
    amount = factory.fuzzy.FuzzyDecimal(5.00, 50.00, 2)
    description = factory.fuzzy.FuzzyChoice([
        "Gear purchase", "Private lesson", "Seminar fee",
        "Payment received", "Refund", "Late fee"
    ])
    billed = False
    stripe_payment_intent_id = ""


class DojoTabBalanceFactory(DjangoModelFactory):
    class Meta:
        model = "membership.DojoTabBalance"

    academy = factory.SubFactory(AcademyFactory)
    athlete = factory.SubFactory(AthleteProfileFactory)
    balance = factory.fuzzy.FuzzyDecimal(-100.00, 100.00, 2)


class AthleteAchievementFactory(DjangoModelFactory):
    class Meta:
        model = "community.AthleteAchievement"

    athlete = factory.SubFactory(AthleteProfileFactory)
    achievement = factory.SubFactory(AchievementFactory)
    awarded_by = factory.SubFactory(AthleteProfileFactory)  # Can be null for automatic awards


class OpenMatRSVPFactory(DjangoModelFactory):
    class Meta:
        model = "community.OpenMatRSVP"

    session = factory.SubFactory(OpenMatSessionFactory)
    athlete = factory.SubFactory(AthleteProfileFactory)
    status = factory.fuzzy.FuzzyChoice(["GOING", "NOT_GOING", "MAYBE"])


# ===== MATCHES APP FACTORIES (stub models) =====


class MatchFactory(DjangoModelFactory):
    class Meta:
        model = "matches.Match"

    academy = factory.SubFactory(AcademyFactory)
    athlete_a = factory.SubFactory("factories.UserFactory")  # Avoid circular import
    athlete_b = factory.SubFactory("factories.UserFactory")
    date = factory.LazyFunction(timezone.now)
    duration_seconds = factory.fuzzy.FuzzyInteger(180, 600)
    is_finished = True
    score_a = factory.fuzzy.FuzzyInteger(0, 12)
    score_b = factory.fuzzy.FuzzyInteger(0, 12)
    winner = factory.SubFactory("factories.UserFactory")  # Can be null for draws


class MatchEventFactory(DjangoModelFactory):
    class Meta:
        model = "matches.MatchEvent"

    match = factory.SubFactory(MatchFactory)
    athlete = factory.SubFactory("factories.UserFactory")  # Should match one of the match athletes
    timestamp = factory.fuzzy.FuzzyInteger(10, 590)  # Within match duration
    points_awarded = factory.fuzzy.FuzzyChoice([2, 3, 4])  # IBJJF scoring
    action_description = factory.fuzzy.FuzzyChoice([
        "Takedown", "Guard pass", "Mount", "Back control",
        "Knee on belly", "Sweep", "Reversal"
    ])
    event_type = "POINTS"


class StripeWebhookEventFactory(DjangoModelFactory):
    class Meta:
        model = "payments.StripeWebhookEvent"

    stripe_event_id = factory.Sequence(lambda n: f"evt_test_{n:010d}")
    event_type = "checkout.session.completed"
    payload = factory.LazyFunction(
        lambda: {"id": "evt_test", "type": "checkout.session.completed"}
    )
    processed = False
