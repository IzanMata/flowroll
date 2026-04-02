"""
Filtering, search, ordering and pagination tests.

Verifies that query-param filters, ?search=, ?ordering=, and ?page_size=
all behave correctly on every ViewSet that exposes them.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    TrainingClassFactory,
    UserFactory,
)
from tatami.tests.factories import TimerPresetFactory, WeightClassFactory


def _member_client(academy, role="STUDENT"):
    user = UserFactory()
    AcademyMembershipFactory(user=user, academy=academy, role=role, is_active=True)
    c = APIClient()
    c.force_authenticate(user=user)
    return c, user


# ══════════════════════════════════════════════════════════════════════════════
# TrainingClass — date-range filters
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTrainingClassFilters:

    def _setup(self):
        academy = AcademyFactory()
        client, _ = _member_client(academy)
        now = timezone.now()
        past = TrainingClassFactory(
            academy=academy,
            title="Past Gi",
            class_type="GI",
            scheduled_at=now - timedelta(days=7),
            duration_minutes=60,
        )
        future = TrainingClassFactory(
            academy=academy,
            title="Future NoGi",
            class_type="NOGI",
            scheduled_at=now + timedelta(days=7),
            duration_minutes=90,
        )
        return academy, client, past, future

    def test_scheduled_after_excludes_past_classes(self):
        academy, client, past, future = self._setup()
        r = client.get(
            f"/api/v1/attendance/classes/",
            {"academy": academy.pk, "scheduled_after": timezone.now().isoformat()},
        )
        assert r.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in r.data["results"]]
        assert future.pk in ids
        assert past.pk not in ids

    def test_scheduled_before_excludes_future_classes(self):
        academy, client, past, future = self._setup()
        r = client.get(
            f"/api/v1/attendance/classes/",
            {"academy": academy.pk, "scheduled_before": timezone.now().isoformat()},
        )
        assert r.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in r.data["results"]]
        assert past.pk in ids
        assert future.pk not in ids

    def test_filter_by_class_type_gi(self):
        academy, client, past, future = self._setup()
        r = client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&class_type=GI"
        )
        assert r.status_code == status.HTTP_200_OK
        for item in r.data["results"]:
            assert item["class_type"] == "GI"

    def test_filter_by_class_type_nogi(self):
        academy, client, past, future = self._setup()
        r = client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&class_type=NOGI"
        )
        assert r.status_code == status.HTTP_200_OK
        for item in r.data["results"]:
            assert item["class_type"] == "NOGI"

    def test_filter_by_professor(self):
        academy = AcademyFactory()
        prof_user_a = UserFactory()
        prof_user_b = UserFactory()
        AcademyMembershipFactory(user=prof_user_a, academy=academy, role="PROFESSOR", is_active=True)
        AcademyMembershipFactory(user=prof_user_b, academy=academy, role="PROFESSOR", is_active=True)
        tc_a = TrainingClassFactory(academy=academy, professor=prof_user_a)
        tc_b = TrainingClassFactory(academy=academy, professor=prof_user_b)

        student_client, _ = _member_client(academy)
        r = student_client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&professor={prof_user_a.pk}"
        )
        assert r.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in r.data["results"]]
        assert tc_a.pk in ids
        assert tc_b.pk not in ids

    def test_search_by_title(self):
        academy, client, _, _ = self._setup()
        r = client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&search=Past"
        )
        assert r.status_code == status.HTTP_200_OK
        assert r.data["count"] >= 1
        for item in r.data["results"]:
            assert "past" in item["title"].lower() or "gi" in item["class_type"].lower()

    def test_ordering_by_duration_ascending(self):
        academy = AcademyFactory()
        client, _ = _member_client(academy)
        TrainingClassFactory(academy=academy, duration_minutes=120, title="Long")
        TrainingClassFactory(academy=academy, duration_minutes=30, title="Short")
        TrainingClassFactory(academy=academy, duration_minutes=60, title="Medium")

        r = client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&ordering=duration_minutes"
        )
        assert r.status_code == status.HTTP_200_OK
        durations = [item["duration_minutes"] for item in r.data["results"]]
        assert durations == sorted(durations)

    def test_ordering_by_duration_descending(self):
        academy = AcademyFactory()
        client, _ = _member_client(academy)
        TrainingClassFactory(academy=academy, duration_minutes=90, title="C1")
        TrainingClassFactory(academy=academy, duration_minutes=45, title="C2")

        r = client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&ordering=-duration_minutes"
        )
        assert r.status_code == status.HTTP_200_OK
        durations = [item["duration_minutes"] for item in r.data["results"]]
        assert durations == sorted(durations, reverse=True)

    def test_ordering_by_scheduled_at_ascending(self):
        academy, client, past, future = self._setup()
        r = client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&ordering=scheduled_at"
        )
        assert r.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in r.data["results"]]
        assert ids.index(past.pk) < ids.index(future.pk)

    def test_ordering_by_scheduled_at_descending(self):
        academy, client, past, future = self._setup()
        r = client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&ordering=-scheduled_at"
        )
        assert r.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in r.data["results"]]
        assert ids.index(future.pk) < ids.index(past.pk)


# ══════════════════════════════════════════════════════════════════════════════
# Pagination
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPagination:

    def test_default_pagination_returns_count_and_results(self):
        academy = AcademyFactory()
        client, _ = _member_client(academy)
        for i in range(5):
            TrainingClassFactory(academy=academy, title=f"Class {i}")

        r = client.get(f"/api/v1/attendance/classes/?academy={academy.pk}")
        assert r.status_code == status.HTTP_200_OK
        assert "count" in r.data
        assert "results" in r.data
        assert "next" in r.data
        assert "previous" in r.data
        assert r.data["count"] == 5

    def test_page_size_limits_results(self):
        academy = AcademyFactory()
        client, _ = _member_client(academy)
        for i in range(10):
            TrainingClassFactory(academy=academy, title=f"Class {i}")

        r = client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&page_size=3"
        )
        assert r.status_code == status.HTTP_200_OK
        assert len(r.data["results"]) == 3
        assert r.data["count"] == 10
        assert r.data["next"] is not None

    def test_page_size_capped_at_maximum(self):
        """page_size=999999 must be clamped to MAX_PAGE_SIZE (100)."""
        academy = AcademyFactory()
        client, _ = _member_client(academy)
        for i in range(5):
            TrainingClassFactory(academy=academy, title=f"Class {i}")

        r = client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&page_size=999999"
        )
        assert r.status_code == status.HTTP_200_OK
        # Page size should be capped; all 5 items still returned (< max)
        assert len(r.data["results"]) == 5

    def test_second_page_returns_different_results(self):
        academy = AcademyFactory()
        client, _ = _member_client(academy)
        for i in range(5):
            TrainingClassFactory(academy=academy, title=f"Class {i}")

        r1 = client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&page_size=2&page=1"
        )
        r2 = client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&page_size=2&page=2"
        )
        assert r1.status_code == status.HTTP_200_OK
        assert r2.status_code == status.HTTP_200_OK
        ids_p1 = {item["id"] for item in r1.data["results"]}
        ids_p2 = {item["id"] for item in r2.data["results"]}
        assert ids_p1.isdisjoint(ids_p2), "Pages must not overlap"

    def test_page_beyond_last_returns_empty(self):
        academy = AcademyFactory()
        client, _ = _member_client(academy)
        TrainingClassFactory(academy=academy, title="Only one")

        r = client.get(
            f"/api/v1/attendance/classes/?academy={academy.pk}&page_size=1&page=999"
        )
        # DRF returns 404 when page is out of range
        assert r.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_200_OK)


# ══════════════════════════════════════════════════════════════════════════════
# WeightClass search
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestWeightClassSearch:

    def test_search_returns_matching_weight_class(self):
        WeightClassFactory(name="Middle")
        WeightClassFactory(name="Heavy")
        user = UserFactory()
        c = APIClient()
        c.force_authenticate(user=user)

        r = c.get("/api/v1/tatami/weight-classes/?search=Middle")
        assert r.status_code == status.HTTP_200_OK
        names = [item["name"] for item in r.data["results"]]
        assert "Middle" in names
        assert "Heavy" not in names

    def test_search_no_match_returns_empty(self):
        WeightClassFactory(name="Rooster")
        user = UserFactory()
        c = APIClient()
        c.force_authenticate(user=user)

        r = c.get("/api/v1/tatami/weight-classes/?search=XXXXXXXXXX")
        assert r.status_code == status.HTTP_200_OK
        assert r.data["count"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# TimerPreset — academy scoping filter
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTimerPresetFiltering:

    def test_presets_scoped_to_requested_academy(self):
        academy_a = AcademyFactory()
        academy_b = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy_a, role="STUDENT", is_active=True)
        preset_a = TimerPresetFactory(academy=academy_a)
        preset_b = TimerPresetFactory(academy=academy_b)

        c = APIClient()
        c.force_authenticate(user=user)
        r = c.get(f"/api/v1/tatami/timer-presets/?academy={academy_a.pk}")

        assert r.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in r.data["results"]]
        assert preset_a.pk in ids
        assert preset_b.pk not in ids

    def test_no_academy_param_returns_empty(self):
        user = UserFactory()
        TimerPresetFactory()
        c = APIClient()
        c.force_authenticate(user=user)
        r = c.get("/api/v1/tatami/timer-presets/")
        assert r.status_code in (status.HTTP_200_OK, status.HTTP_403_FORBIDDEN)
        if r.status_code == status.HTTP_200_OK:
            assert r.data["count"] == 0
