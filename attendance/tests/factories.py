import factory
from factory.django import DjangoModelFactory
import random
from datetime import timedelta
from django.utils import timezone

from attendance.models import TrainingClass, CheckIn, QRCode, DropInVisitor
from academies.tests.factories import AcademyFactory
from athletes.tests.factories import AthleteProfileFactory
from core.tests.factories import UserFactory
from core.seeders.utils import BJJ_TRAINING_CLASS_TITLES, random_past_datetime, random_future_datetime


class TrainingClassFactory(DjangoModelFactory):
    class Meta:
        model = TrainingClass

    academy = factory.SubFactory(AcademyFactory)
    title = factory.Iterator(BJJ_TRAINING_CLASS_TITLES)
    class_type = factory.LazyAttribute(
        lambda obj: random.choice([
            TrainingClass.ClassType.GI,
            TrainingClass.ClassType.NOGI,
            TrainingClass.ClassType.OPEN_MAT,
            TrainingClass.ClassType.KIDS,
            TrainingClass.ClassType.COMPETITION
        ])
    )
    professor = factory.SubFactory(UserFactory)
    scheduled_at = factory.LazyAttribute(lambda obj: random_past_datetime(30))
    duration_minutes = factory.LazyAttribute(lambda obj: random.choice([60, 90, 120]))
    max_capacity = factory.LazyAttribute(lambda obj: random.randint(15, 30))
    notes = factory.Faker("sentence", locale="es_ES")


class CheckInFactory(DjangoModelFactory):
    class Meta:
        model = CheckIn

    athlete = factory.SubFactory(AthleteProfileFactory)
    training_class = factory.SubFactory(TrainingClassFactory)
    method = factory.LazyAttribute(
        lambda obj: random.choice([CheckIn.Method.QR, CheckIn.Method.MANUAL])
    )


class QRCodeFactory(DjangoModelFactory):
    class Meta:
        model = QRCode

    training_class = factory.SubFactory(TrainingClassFactory)
    expires_at = factory.LazyAttribute(
        lambda obj: obj.training_class.scheduled_at + timedelta(hours=2)
    )
    is_active = True


class DropInVisitorFactory(DjangoModelFactory):
    class Meta:
        model = DropInVisitor

    academy = factory.SubFactory(AcademyFactory)
    first_name = factory.Faker("first_name", locale="es_ES")
    last_name = factory.Faker("last_name", locale="es_ES")
    email = factory.Sequence(lambda n: f"visitor{n}@gmail.com")
    phone = factory.Faker("phone_number", locale="es_ES")
    training_class = factory.SubFactory(TrainingClassFactory)
    expires_at = factory.LazyAttribute(lambda obj: timezone.now() + timedelta(days=7))