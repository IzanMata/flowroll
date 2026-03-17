"""
Root conftest.py — shared fixtures available across all test files.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from athletes.models import AthleteProfile
from core.models import AcademyMembership, Belt
from factories import AcademyFactory, AthleteProfileFactory, UserFactory

# ─── Belt fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def belt_white(db):
    return Belt.objects.get_or_create(
        color="white", defaults={"order": 1, "description": ""}
    )[0]


@pytest.fixture
def belt_blue(db):
    return Belt.objects.get_or_create(
        color="blue", defaults={"order": 2, "description": ""}
    )[0]


@pytest.fixture
def belt_purple(db):
    return Belt.objects.get_or_create(
        color="purple", defaults={"order": 3, "description": ""}
    )[0]


@pytest.fixture
def belt_brown(db):
    return Belt.objects.get_or_create(
        color="brown", defaults={"order": 4, "description": ""}
    )[0]


@pytest.fixture
def belt_black(db):
    return Belt.objects.get_or_create(
        color="black", defaults={"order": 5, "description": ""}
    )[0]


# ─── Academy ─────────────────────────────────────────────────────────────────


@pytest.fixture
def academy(db):
    return AcademyFactory()


@pytest.fixture
def second_academy(db):
    return AcademyFactory(name="Second Academy")


# ─── Users ───────────────────────────────────────────────────────────────────


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(username=None, **kwargs):
        counter["n"] += 1
        name = username or f"user{counter['n']}"
        return User.objects.create_user(username=name, password="testpass123", **kwargs)

    return _make


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def professor_user(db):
    return UserFactory(username="professor")


@pytest.fixture
def owner_user(db):
    return UserFactory(username="owner")


# ─── AcademyMembership helpers ───────────────────────────────────────────────


@pytest.fixture
def make_membership(db):
    """Factory: make_membership(user, academy, role='STUDENT')"""

    def _make(user, academy, role="STUDENT"):
        return AcademyMembership.objects.create(
            user=user, academy=academy, role=role, is_active=True
        )

    return _make


# ─── Athletes ─────────────────────────────────────────────────────────────────


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


@pytest.fixture
def athlete(db, academy, belt_white):
    user = UserFactory(username="athlete_user")
    return AthleteProfileFactory(user=user, academy=academy, belt="white")


@pytest.fixture
def professor_athlete(db, academy, professor_user):
    return AthleteProfileFactory(
        user=professor_user, academy=academy, belt="black", role="PROFESSOR"
    )


# ─── API Client ──────────────────────────────────────────────────────────────


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(db, athlete):
    """Authenticated API client for the default athlete."""
    client = APIClient()
    client.force_authenticate(user=athlete.user)
    return client


@pytest.fixture
def professor_client(db, professor_athlete):
    """Authenticated API client for the professor."""
    client = APIClient()
    client.force_authenticate(user=professor_athlete.user)
    return client


@pytest.fixture
def owner_client(db, academy, owner_user):
    AcademyMembership.objects.create(
        user=owner_user, academy=academy, role="OWNER", is_active=True
    )
    client = APIClient()
    client.force_authenticate(user=owner_user)
    return client
