"""
H-1 fix verification: AcademyViewSet permission and tenant-isolation tests.

Covers:
  - Unauthenticated requests are rejected (401)
  - Users only see academies they belong to
  - Owners can update/delete their own academy
  - Non-owners cannot update/delete foreign academies
  - Superusers see all academies
"""

from rest_framework import status

from core.models import AcademyMembership
from factories import AcademyFactory, AcademyMembershipFactory, UserFactory

ACADEMIES_URL = "/api/academies/"


def academy_detail_url(pk):
    return f"{ACADEMIES_URL}{pk}/"


# ─── Authentication guard ─────────────────────────────────────────────────────


class TestAcademyAuthGuard:
    def test_unauthenticated_list_returns_401(self, api_client):
        response = api_client.get(ACADEMIES_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthenticated_detail_returns_401(self, api_client, academy):
        response = api_client.get(academy_detail_url(academy.pk))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── Queryset tenant isolation ────────────────────────────────────────────────


class TestAcademyListIsolation:
    def test_member_sees_own_academy(self, db, auth_client, academy, athlete):
        """auth_client's athlete is a member of `academy`."""
        AcademyMembership.objects.get_or_create(
            user=athlete.user,
            academy=academy,
            defaults={"role": "STUDENT", "is_active": True},
        )
        response = auth_client.get(ACADEMIES_URL)
        assert response.status_code == status.HTTP_200_OK
        returned_ids = [a["id"] for a in response.data["results"]]
        assert academy.pk in returned_ids

    def test_member_does_not_see_foreign_academy(
        self, db, auth_client, academy, athlete
    ):
        """auth_client should NOT see an academy they don't belong to."""
        AcademyMembership.objects.get_or_create(
            user=athlete.user,
            academy=academy,
            defaults={"role": "STUDENT", "is_active": True},
        )
        other = AcademyFactory(name="Foreign Academy")
        response = auth_client.get(ACADEMIES_URL)
        assert response.status_code == status.HTTP_200_OK
        returned_ids = [a["id"] for a in response.data["results"]]
        assert other.pk not in returned_ids

    def test_user_with_no_memberships_sees_empty_list(self, db, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        AcademyFactory()  # exists but user has no membership
        response = api_client.get(ACADEMIES_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_superuser_sees_all_academies(self, db, api_client):
        superuser = UserFactory(is_superuser=True, is_staff=True)
        api_client.force_authenticate(user=superuser)
        AcademyFactory()
        AcademyFactory()
        response = api_client.get(ACADEMIES_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 2


# ─── Mutation permissions ─────────────────────────────────────────────────────


class TestAcademyMutationPermissions:
    def test_owner_can_update_own_academy(self, db, api_client, academy):
        owner = UserFactory()
        AcademyMembershipFactory(
            user=owner, academy=academy, role="OWNER", is_active=True
        )
        api_client.force_authenticate(user=owner)
        response = api_client.patch(academy_detail_url(academy.pk), {"city": "Tokyo"})
        assert response.status_code == status.HTTP_200_OK
        academy.refresh_from_db()
        assert academy.city == "Tokyo"

    def test_student_cannot_update_academy(self, db, api_client, academy):
        student = UserFactory()
        AcademyMembershipFactory(
            user=student, academy=academy, role="STUDENT", is_active=True
        )
        api_client.force_authenticate(user=student)
        response = api_client.patch(academy_detail_url(academy.pk), {"city": "Tokyo"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_cannot_delete_academy(self, db, api_client, academy):
        prof = UserFactory()
        AcademyMembershipFactory(
            user=prof, academy=academy, role="PROFESSOR", is_active=True
        )
        api_client.force_authenticate(user=prof)
        response = api_client.delete(academy_detail_url(academy.pk))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_owner_cannot_update_foreign_academy(self, db, api_client, academy):
        """Being an owner of Academy A grants no rights over Academy B."""
        owner = UserFactory()
        AcademyMembershipFactory(
            user=owner, academy=academy, role="OWNER", is_active=True
        )
        other = AcademyFactory(name="Other Academy")
        api_client.force_authenticate(user=owner)
        response = api_client.patch(academy_detail_url(other.pk), {"city": "Osaka"})
        # 404 because other academy is not in their queryset
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )

    def test_owner_can_delete_academy(self, db, api_client, academy):
        owner = UserFactory()
        AcademyMembershipFactory(
            user=owner, academy=academy, role="OWNER", is_active=True
        )
        api_client.force_authenticate(user=owner)
        response = api_client.delete(academy_detail_url(academy.pk))
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_student_cannot_delete_academy(self, db, api_client, academy):
        student = UserFactory()
        AcademyMembershipFactory(
            user=student, academy=academy, role="STUDENT", is_active=True
        )
        api_client.force_authenticate(user=student)
        response = api_client.delete(academy_detail_url(academy.pk))
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ─── Retrieve detail ──────────────────────────────────────────────────────────


class TestAcademyRetrieve:
    def test_member_can_retrieve_own_academy(self, db, api_client, academy):
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        api_client.force_authenticate(user=user)
        response = api_client.get(academy_detail_url(academy.pk))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == academy.pk
        assert response.data["name"] == academy.name

    def test_non_member_gets_404_on_detail(self, db, api_client, academy):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        response = api_client.get(academy_detail_url(academy.pk))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_detail_response_contains_expected_fields(self, db, api_client, academy):
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        api_client.force_authenticate(user=user)
        response = api_client.get(academy_detail_url(academy.pk))
        assert response.status_code == status.HTTP_200_OK
        for field in ("id", "name", "city", "country", "email", "phone", "website", "is_active", "created_at", "updated_at"):
            assert field in response.data


# ─── Create ───────────────────────────────────────────────────────────────────


class TestAcademyCreate:
    def test_authenticated_user_can_create_academy(self, db, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        response = api_client.post(ACADEMIES_URL, {"name": "New Dojo"})
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Dojo"

    def test_unauthenticated_create_returns_401(self, api_client):
        response = api_client.post(ACADEMIES_URL, {"name": "Sneaky Dojo"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_without_name_returns_400(self, db, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        response = api_client.post(ACADEMIES_URL, {"city": "Tokyo"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ─── Inactive membership ──────────────────────────────────────────────────────


class TestAcademyInactiveMembership:
    def test_inactive_membership_excluded_from_queryset(self, db, api_client, academy):
        user = UserFactory()
        AcademyMembershipFactory(
            user=user, academy=academy, role="STUDENT", is_active=False
        )
        api_client.force_authenticate(user=user)
        response = api_client.get(ACADEMIES_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_inactive_membership_blocks_detail_access(self, db, api_client, academy):
        user = UserFactory()
        AcademyMembershipFactory(
            user=user, academy=academy, role="STUDENT", is_active=False
        )
        api_client.force_authenticate(user=user)
        response = api_client.get(academy_detail_url(academy.pk))
        assert response.status_code == status.HTTP_404_NOT_FOUND
