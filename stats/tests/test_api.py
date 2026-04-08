"""
API tests for the stats app: AthleteStatsViewSet (list, by_athlete,
recompute, leaderboard) and permission enforcement.

Note: All endpoints require ?academy= param because IsAcademyMember
resolves the academy from query params. Without it, the permission
check fails with 403 before the view logic runs.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    UserFactory,
)
from matches.models import Match
from stats.models import AthleteMatchStats

STATS_URL = "/api/v1/stats/"


def by_athlete_url(athlete_pk, academy_pk):
    return f"{STATS_URL}athlete/{athlete_pk}/?academy={academy_pk}"


def recompute_url(athlete_pk, academy_pk):
    return f"{STATS_URL}athlete/{athlete_pk}/recompute/?academy={academy_pk}"


def leaderboard_url(academy_pk=None):
    if academy_pk:
        return f"{STATS_URL}leaderboard/?academy={academy_pk}"
    return f"{STATS_URL}leaderboard/"


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def stats_academy(db):
    return AcademyFactory()


@pytest.fixture
def professor_user(stats_academy):
    user = UserFactory()
    AcademyMembershipFactory(user=user, academy=stats_academy, role="PROFESSOR", is_active=True)
    return user


@pytest.fixture
def student_user(stats_academy):
    user = UserFactory()
    AcademyMembershipFactory(user=user, academy=stats_academy, role="STUDENT", is_active=True)
    return user


@pytest.fixture
def prof_client(professor_user):
    client = APIClient()
    client.force_authenticate(user=professor_user)
    return client


@pytest.fixture
def student_client(student_user):
    client = APIClient()
    client.force_authenticate(user=student_user)
    return client


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture
def athlete_with_stats(stats_academy):
    athlete = AthleteProfileFactory(academy=stats_academy)
    AthleteMatchStats.objects.create(athlete=athlete, total_matches=2, wins=1, losses=1)
    return athlete


# ─── Auth guard ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestStatsAuthGuard:
    def test_unauthenticated_list_returns_401(self, anon_client, stats_academy):
        response = anon_client.get(f"{STATS_URL}?academy={stats_academy.pk}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthenticated_leaderboard_returns_401(self, anon_client, stats_academy):
        response = anon_client.get(leaderboard_url(stats_academy.pk))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── Permission checks ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestStatsPermissions:
    def test_member_can_list_stats(self, student_client, stats_academy, athlete_with_stats):
        response = student_client.get(f"{STATS_URL}?academy={stats_academy.pk}")
        assert response.status_code == status.HTTP_200_OK

    def test_non_member_cannot_list_stats(self, stats_academy, athlete_with_stats):
        outsider = UserFactory()
        client = APIClient()
        client.force_authenticate(user=outsider)
        response = client.get(f"{STATS_URL}?academy={stats_academy.pk}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_member_can_view_by_athlete(self, student_client, stats_academy, athlete_with_stats):
        response = student_client.get(by_athlete_url(athlete_with_stats.pk, stats_academy.pk))
        assert response.status_code == status.HTTP_200_OK

    def test_student_cannot_recompute(self, student_client, stats_academy, athlete_with_stats):
        response = student_client.post(recompute_url(athlete_with_stats.pk, stats_academy.pk))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_recompute(self, prof_client, stats_academy, athlete_with_stats):
        response = prof_client.post(recompute_url(athlete_with_stats.pk, stats_academy.pk))
        assert response.status_code == status.HTTP_200_OK


# ─── Queryset scoping ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestStatsScoping:
    def test_no_academy_param_returns_403(self, student_client):
        # IsAcademyMember requires ?academy= — absent means permission denied.
        response = student_client.get(STATS_URL)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_only_academy_athletes_visible(self, student_client, stats_academy, athlete_with_stats):
        other = AcademyFactory()
        other_athlete = AthleteProfileFactory(academy=other)
        AthleteMatchStats.objects.create(athlete=other_athlete, total_matches=1, wins=1)
        response = student_client.get(f"{STATS_URL}?academy={stats_academy.pk}")
        pks = [r["athlete"] for r in response.data["results"]]
        assert athlete_with_stats.pk in pks
        assert other_athlete.pk not in pks


# ─── by_athlete action ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestByAthleteAction:
    def test_returns_stats_for_athlete(self, student_client, stats_academy, athlete_with_stats):
        response = student_client.get(by_athlete_url(athlete_with_stats.pk, stats_academy.pk))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_matches"] == 2
        assert response.data["wins"] == 1

    def test_returns_404_if_no_stats(self, student_client, stats_academy):
        athlete = AthleteProfileFactory(academy=stats_academy)
        response = student_client.get(by_athlete_url(athlete.pk, stats_academy.pk))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_404_for_unknown_athlete(self, student_client, stats_academy):
        response = student_client.get(by_athlete_url(999999, stats_academy.pk))
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ─── recompute action ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRecomputeAction:
    def test_recompute_creates_stats_from_matches(self, prof_client, stats_academy):
        athlete = AthleteProfileFactory(academy=stats_academy)
        opponent = AthleteProfileFactory(academy=stats_academy)
        Match.objects.create(
            academy=stats_academy,
            athlete_a=athlete.user,
            athlete_b=opponent.user,
            is_finished=True,
            winner=athlete.user,
        )
        response = prof_client.post(recompute_url(athlete.pk, stats_academy.pk))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["wins"] == 1
        assert response.data["total_matches"] == 1

    def test_recompute_updates_stale_stats(self, prof_client, stats_academy):
        athlete = AthleteProfileFactory(academy=stats_academy)
        opponent = AthleteProfileFactory(academy=stats_academy)
        AthleteMatchStats.objects.create(athlete=athlete, total_matches=0, wins=0)
        Match.objects.create(
            academy=stats_academy,
            athlete_a=athlete.user,
            athlete_b=opponent.user,
            is_finished=True,
            winner=athlete.user,
        )
        response = prof_client.post(recompute_url(athlete.pk, stats_academy.pk))
        assert response.data["wins"] == 1

    def test_recompute_athlete_no_stats_returns_200(self, prof_client, stats_academy):
        athlete = AthleteProfileFactory(academy=stats_academy)
        response = prof_client.post(recompute_url(athlete.pk, stats_academy.pk))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["wins"] == 0


# ─── leaderboard action ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestLeaderboardAction:
    def test_no_academy_param_returns_403(self, student_client):
        # IsAcademyMember fires before the view's 400 guard.
        response = student_client.get(leaderboard_url())
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_returns_athletes_ranked_by_wins(self, student_client, stats_academy):
        a1 = AthleteProfileFactory(academy=stats_academy)
        a2 = AthleteProfileFactory(academy=stats_academy)
        AthleteMatchStats.objects.create(athlete=a1, total_matches=2, wins=1)
        AthleteMatchStats.objects.create(athlete=a2, total_matches=3, wins=3)
        response = student_client.get(leaderboard_url(stats_academy.pk))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        assert response.data[0]["wins"] == 3  # top ranked first

    def test_excludes_athletes_with_no_matches(self, student_client, stats_academy):
        athlete = AthleteProfileFactory(academy=stats_academy)
        AthleteMatchStats.objects.create(athlete=athlete, total_matches=0, wins=0)
        response = student_client.get(leaderboard_url(stats_academy.pk))
        assert len(response.data) == 0

    def test_respects_limit_param(self, student_client, stats_academy):
        for _ in range(5):
            a = AthleteProfileFactory(academy=stats_academy)
            AthleteMatchStats.objects.create(athlete=a, total_matches=1, wins=1)
        response = student_client.get(f"{leaderboard_url(stats_academy.pk)}&limit=3")
        assert len(response.data) == 3

    def test_limit_capped_at_100(self, student_client, stats_academy):
        for _ in range(5):
            a = AthleteProfileFactory(academy=stats_academy)
            AthleteMatchStats.objects.create(athlete=a, total_matches=1, wins=1)
        response = student_client.get(f"{leaderboard_url(stats_academy.pk)}&limit=200")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) <= 100

    def test_empty_leaderboard(self, student_client, stats_academy):
        response = student_client.get(leaderboard_url(stats_academy.pk))
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_non_member_cannot_view_leaderboard(self, stats_academy):
        outsider = UserFactory()
        client = APIClient()
        client.force_authenticate(user=outsider)
        a = AthleteProfileFactory(academy=stats_academy)
        AthleteMatchStats.objects.create(athlete=a, total_matches=1, wins=1)
        response = client.get(leaderboard_url(stats_academy.pk))
        assert response.status_code == status.HTTP_403_FORBIDDEN
