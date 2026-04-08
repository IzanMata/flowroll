"""
API tests for the belt promotion readiness endpoints:

  GET /api/v1/athletes/promotion-readiness/?academy=<id>   (professor/owner only)
  GET /api/v1/athletes/<id>/promotion-readiness/?academy=<id>  (academy members)
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    PromotionRequirementFactory,
    UserFactory,
)

LIST_URL = "/api/v1/athletes/promotion-readiness/"


def detail_url(pk, academy_pk):
    return f"/api/v1/athletes/{pk}/promotion-readiness/?academy={academy_pk}"


# ─── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def academy(db):
    return AcademyFactory()


@pytest.fixture
def professor(db, academy):
    user = UserFactory()
    athlete = AthleteProfileFactory(user=user, academy=academy, role="PROFESSOR")
    AcademyMembershipFactory(user=user, academy=academy, role="PROFESSOR", is_active=True)
    return athlete


@pytest.fixture
def owner(db, academy):
    user = UserFactory()
    athlete = AthleteProfileFactory(user=user, academy=academy, role="PROFESSOR")
    AcademyMembershipFactory(user=user, academy=academy, role="OWNER", is_active=True)
    return athlete


@pytest.fixture
def student(db, academy):
    user = UserFactory()
    athlete = AthleteProfileFactory(
        user=user, academy=academy, role="STUDENT",
        belt="white", stripes=4, mat_hours=200.0,
        belt_awarded_at=timezone.now() - timedelta(days=400),
    )
    AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
    return athlete


@pytest.fixture
def requirement(db, academy):
    return PromotionRequirementFactory(
        academy=None,  # global
        belt="blue",
        min_mat_hours=100.0,
        min_months_at_belt=6,
        min_stripes_before_promotion=4,
    )


@pytest.fixture
def prof_client(professor):
    client = APIClient()
    client.force_authenticate(user=professor.user)
    return client


@pytest.fixture
def owner_client(owner):
    client = APIClient()
    client.force_authenticate(user=owner.user)
    return client


@pytest.fixture
def student_client(student):
    client = APIClient()
    client.force_authenticate(user=student.user)
    return client


# ─── List endpoint ─────────────────────────────────────────────────────────────


class TestPromotionReadinessList:
    def test_requires_auth(self, db, academy):
        client = APIClient()
        resp = client.get(LIST_URL, {"academy": academy.pk})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_student_forbidden(self, db, student_client, academy, requirement):
        resp = student_client.get(LIST_URL, {"academy": academy.pk})
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_access(self, db, prof_client, academy, student, requirement):
        resp = prof_client.get(LIST_URL, {"academy": academy.pk})
        assert resp.status_code == status.HTTP_200_OK

    def test_owner_can_access(self, db, owner_client, academy, student, requirement):
        resp = owner_client.get(LIST_URL, {"academy": academy.pk})
        assert resp.status_code == status.HTTP_200_OK

    def test_missing_academy_param_returns_4xx(self, db, prof_client):
        # Without ?academy=, IsAcademyProfessor cannot resolve membership → 403
        resp = prof_client.get(LIST_URL)
        assert resp.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN)

    def test_response_shape(self, db, prof_client, academy, student, requirement):
        resp = prof_client.get(LIST_URL, {"academy": academy.pk})
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        item = next(r for r in data if r["athlete_id"] == student.pk)
        expected_keys = {
            "athlete_id", "current_belt", "next_belt", "requirement_found",
            "is_ready", "mat_hours_ok", "mat_hours_current", "mat_hours_required",
            "months_ok", "months_current", "months_required",
            "stripes_ok", "stripes_current", "stripes_required",
        }
        assert expected_keys.issubset(item.keys())

    def test_ready_athlete_flagged(self, db, prof_client, academy, student, requirement):
        resp = prof_client.get(LIST_URL, {"academy": academy.pk})
        data = resp.json()
        item = next(r for r in data if r["athlete_id"] == student.pk)
        assert item["is_ready"] is True

    def test_not_ready_athlete_flagged(self, db, prof_client, academy, requirement):
        not_ready = AthleteProfileFactory(
            academy=academy, belt="white", stripes=0,
            mat_hours=5.0, belt_awarded_at=None,
        )
        AcademyMembershipFactory(
            user=not_ready.user, academy=academy, role="STUDENT", is_active=True
        )
        resp = prof_client.get(LIST_URL, {"academy": academy.pk})
        data = resp.json()
        item = next((r for r in data if r["athlete_id"] == not_ready.pk), None)
        assert item is not None
        assert item["is_ready"] is False

    def test_cross_academy_isolation(self, db, prof_client, academy, requirement):
        other_academy = AcademyFactory()
        other_athlete = AthleteProfileFactory(academy=other_academy, belt="white")
        resp = prof_client.get(LIST_URL, {"academy": academy.pk})
        data = resp.json()
        ids = {r["athlete_id"] for r in data}
        assert other_athlete.pk not in ids


# ─── Detail endpoint ───────────────────────────────────────────────────────────


class TestPromotionReadinessDetail:
    def test_requires_auth(self, db, academy, student):
        client = APIClient()
        resp = client.get(detail_url(student.pk, academy.pk))
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_member_forbidden(self, db, academy, student):
        outsider = UserFactory()
        client = APIClient()
        client.force_authenticate(user=outsider)
        resp = client.get(detail_url(student.pk, academy.pk))
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_student_can_view_own_readiness(self, db, student_client, academy, student, requirement):
        resp = student_client.get(detail_url(student.pk, academy.pk))
        assert resp.status_code == status.HTTP_200_OK

    def test_professor_can_view_any_athlete(self, db, prof_client, academy, student, requirement):
        resp = prof_client.get(detail_url(student.pk, academy.pk))
        assert resp.status_code == status.HTTP_200_OK

    def test_response_shape(self, db, prof_client, academy, student, requirement):
        resp = prof_client.get(detail_url(student.pk, academy.pk))
        data = resp.json()
        assert data["athlete_id"] == student.pk
        assert data["current_belt"] == "white"
        assert data["next_belt"] == "blue"
        assert "is_ready" in data

    def test_no_requirement_returns_not_ready(self, db, prof_client, academy, student):
        # No PromotionRequirement exists
        resp = prof_client.get(detail_url(student.pk, academy.pk))
        data = resp.json()
        assert data["requirement_found"] is False
        assert data["is_ready"] is False

    def test_black_belt_no_next_belt(self, db, prof_client, academy):
        black = AthleteProfileFactory(academy=academy, belt="black", stripes=0)
        AcademyMembershipFactory(
            user=black.user, academy=academy, role="STUDENT", is_active=True
        )
        resp = prof_client.get(detail_url(black.pk, academy.pk))
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["next_belt"] is None
        assert data["is_ready"] is False
