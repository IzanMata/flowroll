import factory
from factory.django import DjangoModelFactory
from django.contrib.auth import get_user_model

User = get_user_model()


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.Sequence(lambda n: f"user{n}@flowroll.com")
    first_name = factory.Faker("first_name", locale="es_ES")
    last_name = factory.Faker("last_name", locale="es_ES")
    password = factory.PostGenerationMethodCall('set_password', 'FlowRoll2024!')
    is_active = True
    is_staff = False
    is_superuser = False


class SuperUserFactory(UserFactory):
    username = "admin"
    email = "admin@flowroll.com"
    is_staff = True
    is_superuser = True


class ProfessorFactory(UserFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"professor{n}")
    email = factory.Sequence(lambda n: f"professor{n}@flowroll.com")
    first_name = factory.Faker("first_name", locale="es_ES")
    last_name = factory.Faker("last_name", locale="es_ES")


class StudentFactory(UserFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"student{n}")
    email = factory.Sequence(lambda n: f"student{n}@flowroll.com")
    first_name = factory.Faker("first_name", locale="es_ES")
    last_name = factory.Faker("last_name", locale="es_ES")