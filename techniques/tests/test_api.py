"""
H-3 fix verification: Technique and Belt ViewSet permission tests.

Covers:
  - Unauthenticated requests are rejected (401)
  - Authenticated users can READ techniques and belts
  - Non-superusers cannot write (create/update/delete) techniques
  - Superusers can write techniques
  - BeltViewSet is strictly read-only (no write methods exposed)
"""
import pytest
from rest_framework import status

from factories import UserFactory


TECHNIQUES_URL = "/api/techniques/techniques/"
BELTS_URL = "/api/techniques/belts/"
CATEGORIES_URL = "/api/techniques/categories/"


# ─── Authentication guard ─────────────────────────────────────────────────────

class TestTechniqueAuthGuard:
    def test_unauthenticated_technique_list_returns_401(self, api_client):
        response = api_client.get(TECHNIQUES_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthenticated_belt_list_returns_401(self, api_client):
        response = api_client.get(BELTS_URL)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── Read access ─────────────────────────────────────────────────────────────

class TestTechniqueReadAccess:
    def test_authenticated_user_can_list_techniques(self, auth_client):
        response = auth_client.get(TECHNIQUES_URL)
        assert response.status_code == status.HTTP_200_OK

    def test_authenticated_user_can_list_belts(self, auth_client, belt_white):
        response = auth_client.get(BELTS_URL)
        assert response.status_code == status.HTTP_200_OK

    def test_authenticated_user_can_list_categories(self, auth_client):
        response = auth_client.get(CATEGORIES_URL)
        assert response.status_code == status.HTTP_200_OK


# ─── Write restrictions ───────────────────────────────────────────────────────

class TestTechniqueWriteRestrictions:
    def test_regular_user_cannot_create_technique(self, auth_client):
        response = auth_client.post(
            TECHNIQUES_URL,
            {"name": "Armbar", "difficulty": 2, "min_belt": "white"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_superuser_can_create_technique(self, db, api_client):
        superuser = UserFactory(is_superuser=True, is_staff=True)
        api_client.force_authenticate(user=superuser)
        response = api_client.post(
            TECHNIQUES_URL,
            {"name": "Flying Armbar", "difficulty": 4, "min_belt": "blue"},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_regular_user_cannot_create_category(self, auth_client):
        response = auth_client.post(CATEGORIES_URL, {"name": "Leg Locks"})
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ─── Belt is read-only ────────────────────────────────────────────────────────

class TestBeltReadOnly:
    def test_superuser_cannot_create_belt_via_api(self, db, api_client):
        """BeltViewSet is ReadOnlyModelViewSet — POST must return 405 for everyone."""
        superuser = UserFactory(is_superuser=True, is_staff=True)
        api_client.force_authenticate(user=superuser)
        response = api_client.post(BELTS_URL, {"color": "red", "order": 6})
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_regular_user_cannot_create_belt_via_api(self, auth_client):
        response = auth_client.post(BELTS_URL, {"color": "coral", "order": 7})
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
