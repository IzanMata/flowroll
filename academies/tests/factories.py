import factory
from factory.django import DjangoModelFactory
import random

from academies.models import Academy
from core.models import AcademyMembership
from core.tests.factories import UserFactory, ProfessorFactory, StudentFactory
from core.seeders.utils import BJJ_ACADEMY_NAMES


class AcademyFactory(DjangoModelFactory):
    class Meta:
        model = Academy

    name = factory.Sequence(lambda n: BJJ_ACADEMY_NAMES[n % len(BJJ_ACADEMY_NAMES)])


class AcademyMembershipFactory(DjangoModelFactory):
    class Meta:
        model = AcademyMembership

    user = factory.SubFactory(UserFactory)
    academy = factory.SubFactory(AcademyFactory)
    role = factory.LazyAttribute(lambda obj: random.choice([AcademyMembership.Role.STUDENT, AcademyMembership.Role.PROFESSOR]))
    is_active = True