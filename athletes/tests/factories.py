import factory
from factory.django import DjangoModelFactory
import random

from athletes.models import AthleteProfile
from academies.tests.factories import AcademyFactory
from core.tests.factories import UserFactory
from core.models import Belt


class AthleteProfileFactory(DjangoModelFactory):
    class Meta:
        model = AthleteProfile

    user = factory.SubFactory(UserFactory)
    academy = factory.SubFactory(AcademyFactory)
    role = factory.LazyAttribute(lambda obj: random.choice([AthleteProfile.RoleChoices.STUDENT, AthleteProfile.RoleChoices.PROFESSOR]))
    belt = factory.LazyAttribute(lambda obj: random.choice([Belt.BeltColor.WHITE, Belt.BeltColor.BLUE, Belt.BeltColor.PURPLE, Belt.BeltColor.BROWN, Belt.BeltColor.BLACK]))
    stripes = factory.LazyAttribute(lambda obj: random.randint(0, 4))
    weight = factory.LazyAttribute(lambda obj: random.uniform(50.0, 120.0))