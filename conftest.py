"""
Global pytest fixtures for FlowRoll tests.
Available in every test file without import.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Belt
from factories import (
    AcademyFactory,
    AthleteProfileFactory,
    BeltFactory,
    UserFactory,
)


# ─── Belt fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def belt_white(db):
    return BeltFactory(color="white", order=1)


@pytest.fixture
def belt_blue(db):
    return BeltFactory(color="blue", order=2)


@pytest.fixture
def belt_purple(db):
    return BeltFactory(color="purple", order=3)


@pytest.fixture
def belt_brown(db):
    return BeltFactory(color="brown", order=4)


@pytest.fixture
def belt_black(db):
    return BeltFactory(color="black", order=5)


# ─── Core fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def academy(db):
    """Single test academy."""
    return AcademyFactory()


@pytest.fixture
def make_user(db):
    """Factory for creating users with unique usernames."""
    def _make_user(**kwargs):
        return UserFactory(**kwargs)
    return _make_user


@pytest.fixture
def make_athlete(db):
    """Factory for creating athlete profiles."""
    def _make_athlete(belt=None, stripes=0, weight=70.0, **kwargs):
        # Ensure we have a belt instance
        if belt is None:
            belt = "white"

        return AthleteProfileFactory(
            belt=belt,
            stripes=stripes,
            weight=weight,
            **kwargs
        )
    return _make_athlete


@pytest.fixture
def athlete(db):
    """Single test athlete profile."""
    return AthleteProfileFactory()


@pytest.fixture
def professor_athlete(db):
    """Single test professor profile."""
    return AthleteProfileFactory(role="PROFESSOR")


@pytest.fixture
def professor_membership(db, academy, professor_athlete):
    """Professor membership for test academy."""
    from core.models import AcademyMembership
    return AcademyMembership.objects.get_or_create(
        user=professor_athlete.user,
        academy=academy,
        defaults={"role": "PROFESSOR", "is_active": True},
    )[0]


# ─── API Client fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def api_client():
    """Unauthenticated DRF API client."""
    return APIClient()


@pytest.fixture
def auth_client(athlete):
    """Authenticated DRF API client for the test athlete."""
    client = APIClient()
    client.force_authenticate(user=athlete.user)
    return client


@pytest.fixture
def professor_client(professor_athlete):
    """Authenticated DRF API client for a professor."""
    client = APIClient()
    client.force_authenticate(user=professor_athlete.user)
    return client


@pytest.fixture
def admin_client(db):
    """Authenticated DRF API client for a superuser."""
    admin_user = UserFactory(is_superuser=True, is_staff=True)
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client