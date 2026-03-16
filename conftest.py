import pytest
from django.contrib.auth.models import User

from academies.models import Academy
from athletes.models import AthleteProfile
from core.models import Belt


@pytest.fixture
def belt_white(db):
    return Belt.objects.create(color="white", order=1)


@pytest.fixture
def belt_blue(db):
    return Belt.objects.create(color="blue", order=2)


@pytest.fixture
def belt_purple(db):
    return Belt.objects.create(color="purple", order=3)


@pytest.fixture
def belt_brown(db):
    return Belt.objects.create(color="brown", order=4)


@pytest.fixture
def belt_black(db):
    return Belt.objects.create(color="black", order=5)


@pytest.fixture
def academy(db):
    return Academy.objects.create(name="Test Academy", city="Test City")


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(username=None, **kwargs):
        counter["n"] += 1
        name = username or f"user{counter['n']}"
        return User.objects.create_user(username=name, password="testpass123")

    return _make


@pytest.fixture
def make_athlete(db, academy, belt_white, make_user):
    def _make(belt=None, stripes=0, weight=70.0, **kwargs):
        user = make_user()
        return AthleteProfile.objects.create(
            user=user,
            academy=academy,
            belt=(belt or belt_white).color,
            stripes=stripes,
            weight=weight,
            **kwargs,
        )

    return _make
