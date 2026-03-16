"""
H-2 fix verification: AthleteProfileViewSet tenant-isolation tests.

Covers:
  - Unauthenticated requests are rejected (401)
  - Without academy_id param, empty list is returned (not all athletes)
  - User cannot see athletes from an academy they don't belong to
  - User can see athletes from their own academy
  - Non-professor/non-owner cannot update another athlete's profile
  - Athlete can update their own profile
  - Professor can update athletes in their academy
"""
import pytest
from rest_framework import status

from core.models import AcademyMembership
from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    UserFactory,
)


ATHLETES_URL = "/api/athletes/"


def athlete_detail_url(pk):
    return f"{ATHLETES_URL}{pk}/"


# ─── Authentication guard ─────────────────────────────────────────────────────

class TestAthleteAuthGuard:
    def test_unauthenticated_returns_401(self, api_client):
        response = api_client.get(ATHLETES_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── Queryset tenant isolation ────────────────────────────────────────────────

class TestAthleteQuerysetIsolation:
    def test_no_academy_param_returns_empty_list(self, auth_client):
        """Without ?academy_id=, return nothing (not the whole table)."""
        response = auth_client.get(ATHLETES_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_member_can_see_own_academy_athletes(self, db, api_client, academy):
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        AthleteProfileFactory(academy=academy)
        api_client.force_authenticate(user=user)
        response = api_client.get(f"{ATHLETES_URL}?academy_id={academy.pk}")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_non_member_cannot_see_foreign_academy_athletes(self, db, api_client, academy):
        """A user with no membership in `academy` gets an empty queryset, not a 403,
        to avoid leaking the existence of the academy."""
        outsider = UserFactory()
        AthleteProfileFactory(academy=academy)
        api_client.force_authenticate(user=outsider)
        response = api_client.get(f"{ATHLETES_URL}?academy_id={academy.pk}")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_inactive_member_cannot_see_athletes(self, db, api_client, academy):
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=False)
        AthleteProfileFactory(academy=academy)
        api_client.force_authenticate(user=user)
        response = api_client.get(f"{ATHLETES_URL}?academy_id={academy.pk}")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0


# ─── Mutation permissions ─────────────────────────────────────────────────────

class TestAthleteProfileMutations:
    def test_student_cannot_update_another_athletes_profile(
        self, db, api_client, academy
    ):
        owner_user = UserFactory()
        other_user = UserFactory()
        AcademyMembershipFactory(user=owner_user, academy=academy, role="STUDENT", is_active=True)
        target_profile = AthleteProfileFactory(user=other_user, academy=academy)
        api_client.force_authenticate(user=owner_user)
        response = api_client.patch(
            athlete_detail_url(target_profile.pk), {"stripes": 4}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_athlete_can_update_own_profile(self, db, api_client, academy):
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        profile = AthleteProfileFactory(user=user, academy=academy)
        api_client.force_authenticate(user=user)
        response = api_client.patch(athlete_detail_url(profile.pk), {"stripes": 2})
        assert response.status_code == status.HTTP_200_OK

    def test_professor_can_update_academy_athlete(self, db, api_client, academy):
        prof = UserFactory()
        student_user = UserFactory()
        AcademyMembershipFactory(user=prof, academy=academy, role="PROFESSOR", is_active=True)
        profile = AthleteProfileFactory(user=student_user, academy=academy)
        api_client.force_authenticate(user=prof)
        response = api_client.patch(athlete_detail_url(profile.pk), {"stripes": 3})
        assert response.status_code == status.HTTP_200_OK
