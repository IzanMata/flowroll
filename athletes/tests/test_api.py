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

from rest_framework import status

from factories import (AcademyMembershipFactory, AthleteProfileFactory,
                       UserFactory)

ATHLETES_URL = "/api/v1/athletes/"


def athlete_detail_url(pk):
    return f"{ATHLETES_URL}{pk}/"


def athlete_scoped_url(pk, academy_pk):
    """Detail URL with ?academy= so filter_by_academy includes the object."""
    return f"{ATHLETES_URL}{pk}/?academy={academy_pk}"


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
        AcademyMembershipFactory(
            user=user, academy=academy, role="STUDENT", is_active=True
        )
        AthleteProfileFactory(academy=academy)
        api_client.force_authenticate(user=user)
        response = api_client.get(f"{ATHLETES_URL}?academy={academy.pk}")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_non_member_cannot_see_foreign_academy_athletes(
        self, db, api_client, academy
    ):
        """A user with no active membership is denied access (IsAcademyMember → 403)."""
        outsider = UserFactory()
        AthleteProfileFactory(academy=academy)
        api_client.force_authenticate(user=outsider)
        response = api_client.get(f"{ATHLETES_URL}?academy={academy.pk}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_inactive_member_cannot_see_athletes(self, db, api_client, academy):
        """Inactive membership is treated as no membership (IsAcademyMember → 403)."""
        user = UserFactory()
        AcademyMembershipFactory(
            user=user, academy=academy, role="STUDENT", is_active=False
        )
        AthleteProfileFactory(academy=academy)
        api_client.force_authenticate(user=user)
        response = api_client.get(f"{ATHLETES_URL}?academy={academy.pk}")
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ─── Mutation permissions ─────────────────────────────────────────────────────


class TestAthleteProfileMutations:
    def test_student_cannot_update_another_athletes_profile(
        self, db, api_client, academy
    ):
        owner_user = UserFactory()
        other_user = UserFactory()
        AcademyMembershipFactory(
            user=owner_user, academy=academy, role="STUDENT", is_active=True
        )
        target_profile = AthleteProfileFactory(user=other_user, academy=academy)
        api_client.force_authenticate(user=owner_user)
        response = api_client.patch(
            athlete_scoped_url(target_profile.pk, academy.pk), {"stripes": 4}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_athlete_can_update_own_profile(self, db, api_client, academy):
        user = UserFactory()
        AcademyMembershipFactory(
            user=user, academy=academy, role="STUDENT", is_active=True
        )
        profile = AthleteProfileFactory(user=user, academy=academy)
        api_client.force_authenticate(user=user)
        response = api_client.patch(
            athlete_scoped_url(profile.pk, academy.pk), {"stripes": 2}
        )
        assert response.status_code == status.HTTP_200_OK

    def test_professor_can_update_academy_athlete(self, db, api_client, academy):
        prof = UserFactory()
        student_user = UserFactory()
        AcademyMembershipFactory(
            user=prof, academy=academy, role="PROFESSOR", is_active=True
        )
        profile = AthleteProfileFactory(user=student_user, academy=academy)
        api_client.force_authenticate(user=prof)
        response = api_client.patch(
            athlete_scoped_url(profile.pk, academy.pk), {"stripes": 3}
        )
        assert response.status_code == status.HTTP_200_OK

    def test_owner_can_update_any_profile(self, db, api_client, academy):
        owner_user = UserFactory()
        AcademyMembershipFactory(user=owner_user, academy=academy, role="OWNER")
        student = AthleteProfileFactory(academy=academy, stripes=0)
        api_client.force_authenticate(user=owner_user)
        response = api_client.patch(
            athlete_scoped_url(student.pk, academy.pk), {"stripes": 3}
        )
        assert response.status_code == status.HTTP_200_OK
        student.refresh_from_db()
        assert student.stripes == 3

    def test_superuser_can_update_any_profile(self, db, api_client):
        superuser = UserFactory(is_superuser=True, is_staff=True)
        athlete = AthleteProfileFactory(belt="white")
        api_client.force_authenticate(user=superuser)
        response = api_client.patch(
            athlete_scoped_url(athlete.pk, athlete.academy.pk), {"belt": "black"}
        )
        assert response.status_code == status.HTTP_200_OK
        athlete.refresh_from_db()
        assert athlete.belt == "black"

    def test_unauthenticated_update_returns_401(self, db, api_client):
        athlete = AthleteProfileFactory()
        response = api_client.patch(athlete_detail_url(athlete.pk), {"stripes": 1})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── Destroy permissions ──────────────────────────────────────────────────────


class TestAthleteDestroyPermissions:
    def test_user_can_delete_own_profile(self, db, api_client, academy):
        from athletes.models import AthleteProfile
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT")
        athlete = AthleteProfileFactory(user=user, academy=academy)
        api_client.force_authenticate(user=user)
        response = api_client.delete(athlete_scoped_url(athlete.pk, academy.pk))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not AthleteProfile.objects.filter(pk=athlete.pk).exists()

    def test_student_cannot_delete_other_athletes_profile(self, db, api_client, academy):
        from athletes.models import AthleteProfile
        student_user = UserFactory()
        AcademyMembershipFactory(user=student_user, academy=academy, role="STUDENT")
        target = AthleteProfileFactory(academy=academy)
        api_client.force_authenticate(user=student_user)
        response = api_client.delete(athlete_scoped_url(target.pk, academy.pk))
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert AthleteProfile.objects.filter(pk=target.pk).exists()

    def test_professor_can_delete_student_profile(self, db, api_client, academy):
        from athletes.models import AthleteProfile
        professor_user = UserFactory()
        AcademyMembershipFactory(user=professor_user, academy=academy, role="PROFESSOR")
        student = AthleteProfileFactory(academy=academy)
        api_client.force_authenticate(user=professor_user)
        response = api_client.delete(athlete_scoped_url(student.pk, academy.pk))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not AthleteProfile.objects.filter(pk=student.pk).exists()

    def test_superuser_can_delete_any_profile(self, db, api_client):
        from athletes.models import AthleteProfile
        superuser = UserFactory(is_superuser=True, is_staff=True)
        athlete = AthleteProfileFactory()
        api_client.force_authenticate(user=superuser)
        response = api_client.delete(athlete_scoped_url(athlete.pk, athlete.academy.pk))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not AthleteProfile.objects.filter(pk=athlete.pk).exists()


# ─── Serializer fields ────────────────────────────────────────────────────────


class TestAthleteSerializerFields:
    def test_response_contains_username_and_email(self, db, api_client, academy):
        user = UserFactory(username="fighter", email="fighter@bjj.com")
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT")
        athlete = AthleteProfileFactory(user=user, academy=academy)
        api_client.force_authenticate(user=user)
        response = api_client.get(athlete_scoped_url(athlete.pk, academy.pk))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["username"] == "fighter"
        assert response.data["email"] == "fighter@bjj.com"

    def test_response_contains_academy_detail(self, db, api_client, academy):
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT")
        athlete = AthleteProfileFactory(user=user, academy=academy)
        api_client.force_authenticate(user=user)
        response = api_client.get(athlete_scoped_url(athlete.pk, academy.pk))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["academy_detail"]["id"] == academy.pk


# ─── Read-only field enforcement ──────────────────────────────────────────────


class TestAthleteReadOnlyFields:
    """PATCH cannot escalate role or modify system-managed fields."""

    def test_cannot_escalate_role_via_patch(self, db, api_client, academy):
        """A student PATCHing their own profile cannot change their role to PROFESSOR."""
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        profile = AthleteProfileFactory(user=user, academy=academy, role="STUDENT")
        api_client.force_authenticate(user=user)
        response = api_client.patch(
            athlete_scoped_url(profile.pk, academy.pk),
            {"role": "PROFESSOR"},
        )
        # Request may succeed (200) but role must not change
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST)
        profile.refresh_from_db()
        assert profile.role == "STUDENT"

    def test_cannot_inflate_mat_hours_via_patch(self, db, api_client, academy):
        """mat_hours is read-only — PATCH with mat_hours must not change the value."""
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        profile = AthleteProfileFactory(user=user, academy=academy, mat_hours=10.0)
        original_hours = profile.mat_hours
        api_client.force_authenticate(user=user)
        response = api_client.patch(
            athlete_scoped_url(profile.pk, academy.pk),
            {"mat_hours": 9999.0},
        )
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST)
        profile.refresh_from_db()
        assert profile.mat_hours == original_hours

    def test_cannot_change_academy_via_patch(self, db, api_client, academy):
        """academy is read-only — PATCH with a different academy must not move the profile."""
        other_academy = AcademyMembershipFactory().academy
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        profile = AthleteProfileFactory(user=user, academy=academy)
        api_client.force_authenticate(user=user)
        response = api_client.patch(
            athlete_scoped_url(profile.pk, academy.pk),
            {"academy": other_academy.pk},
        )
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST)
        profile.refresh_from_db()
        assert profile.academy_id == academy.pk

    def test_professor_cannot_escalate_to_owner(self, db, api_client, academy):
        """A professor cannot PATCH their own profile to become OWNER."""
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="PROFESSOR", is_active=True)
        profile = AthleteProfileFactory(user=user, academy=academy, role="PROFESSOR")
        api_client.force_authenticate(user=user)
        response = api_client.patch(
            athlete_scoped_url(profile.pk, academy.pk),
            {"role": "OWNER"},
        )
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST)
        profile.refresh_from_db()
        assert profile.role == "PROFESSOR"
