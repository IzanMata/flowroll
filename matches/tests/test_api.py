"""
H-4 fix verification: MatchViewSet permission, scoping, and winner validation tests.

Covers:
  - Unauthenticated requests are rejected (401)
  - Non-professor cannot call match endpoints
  - Queryset is scoped to the academy query param
  - finish_match rejects a winner_id that is not a participant
  - finish_match accepts a valid participant as winner
  - add_event rejects an athlete not in the match
"""

import pytest
from rest_framework import status

from factories import AcademyFactory, AcademyMembershipFactory, UserFactory

MATCHES_URL = "/api/v1/matches/"


def match_detail_url(pk):
    return f"{MATCHES_URL}{pk}/"


def finish_url(pk):
    return f"{MATCHES_URL}{pk}/finish_match/"


def add_event_url(pk):
    return f"{MATCHES_URL}{pk}/add_event/"


@pytest.fixture
def match_academy(db):
    return AcademyFactory(name="Match Academy")


@pytest.fixture
def professor_user(db, match_academy):
    user = UserFactory(username="match_professor")
    AcademyMembershipFactory(
        user=user, academy=match_academy, role="PROFESSOR", is_active=True
    )
    return user


@pytest.fixture
def student_user(db, match_academy):
    user = UserFactory(username="match_student")
    AcademyMembershipFactory(
        user=user, academy=match_academy, role="STUDENT", is_active=True
    )
    return user


@pytest.fixture
def match_obj(db, match_academy, professor_user):
    """A minimal match record; uses User directly per matches.models.Match."""
    from matches.models import Match

    athlete_a = UserFactory(username="fighter_a")
    athlete_b = UserFactory(username="fighter_b")
    return Match.objects.create(
        academy=match_academy,
        athlete_a=athlete_a,
        athlete_b=athlete_b,
    )


# ─── Authentication guard ─────────────────────────────────────────────────────


class TestMatchAuthGuard:
    def test_unauthenticated_list_returns_401(self, api_client, match_academy):
        response = api_client.get(f"{MATCHES_URL}?academy={match_academy.pk}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── Permission guard ─────────────────────────────────────────────────────────


class TestMatchPermissions:
    def test_student_member_can_list_matches(
        self, api_client, student_user, match_academy
    ):
        # Students (academy members) may read matches — only writes require professor.
        api_client.force_authenticate(user=student_user)
        response = api_client.get(f"{MATCHES_URL}?academy={match_academy.pk}")
        assert response.status_code == status.HTTP_200_OK

    def test_non_member_cannot_list_matches(
        self, api_client, match_academy
    ):
        outsider = UserFactory(username="outsider_no_membership")
        api_client.force_authenticate(user=outsider)
        response = api_client.get(f"{MATCHES_URL}?academy={match_academy.pk}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_create_match(
        self, api_client, student_user, match_academy
    ):
        api_client.force_authenticate(user=student_user)
        response = api_client.post(
            f"{MATCHES_URL}?academy={match_academy.pk}",
            data={"academy": match_academy.pk},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_list_matches(
        self, api_client, professor_user, match_academy
    ):
        api_client.force_authenticate(user=professor_user)
        response = api_client.get(f"{MATCHES_URL}?academy={match_academy.pk}")
        assert response.status_code == status.HTTP_200_OK


# ─── Queryset scoping ─────────────────────────────────────────────────────────


class TestMatchQuerysetScoping:
    def test_no_academy_param_returns_empty(self, api_client, professor_user):
        api_client.force_authenticate(user=professor_user)
        response = api_client.get(MATCHES_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_foreign_academy_matches_not_visible(
        self, api_client, professor_user, match_academy, match_obj
    ):
        other_academy = AcademyFactory(name="Other Academy")
        api_client.force_authenticate(user=professor_user)
        response = api_client.get(f"{MATCHES_URL}?academy={other_academy.pk}")
        # Professor is not a member of other_academy → 403 from IsAcademyProfessor
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ─── finish_match winner validation (H-4 fix) ────────────────────────────────


class TestFinishMatch:
    def test_valid_winner_finishes_match(
        self, api_client, professor_user, match_academy, match_obj
    ):
        api_client.force_authenticate(user=professor_user)
        response = api_client.post(
            f"{finish_url(match_obj.pk)}?academy={match_academy.pk}",
            {"winner_id": match_obj.athlete_a_id},
        )
        assert response.status_code == status.HTTP_200_OK
        match_obj.refresh_from_db()
        assert match_obj.is_finished is True
        assert match_obj.winner_id == match_obj.athlete_a_id

    def test_arbitrary_user_as_winner_is_rejected(
        self, api_client, professor_user, match_academy, match_obj
    ):
        """winner_id must be athlete_a or athlete_b — not any arbitrary user id."""
        stranger = UserFactory(username="stranger")
        api_client.force_authenticate(user=professor_user)
        response = api_client.post(
            f"{finish_url(match_obj.pk)}?academy={match_academy.pk}",
            {"winner_id": stranger.pk},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        match_obj.refresh_from_db()
        assert match_obj.is_finished is False

    def test_missing_winner_id_returns_400(
        self, api_client, professor_user, match_academy, match_obj
    ):
        api_client.force_authenticate(user=professor_user)
        response = api_client.post(
            f"{finish_url(match_obj.pk)}?academy={match_academy.pk}",
            {},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_student_cannot_finish_match(
        self, api_client, student_user, match_academy, match_obj
    ):
        api_client.force_authenticate(user=student_user)
        response = api_client.post(
            f"{finish_url(match_obj.pk)}?academy={match_academy.pk}",
            {"winner_id": match_obj.athlete_a_id},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        match_obj.refresh_from_db()
        assert match_obj.is_finished is False

    def test_unauthenticated_cannot_finish_match(self, api_client, match_academy, match_obj):
        response = api_client.post(
            f"{finish_url(match_obj.pk)}?academy={match_academy.pk}",
            {"winner_id": match_obj.athlete_a_id},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── add_event action ─────────────────────────────────────────────────────────


class TestAddEvent:
    def test_professor_can_add_event(
        self, api_client, professor_user, match_academy, match_obj
    ):
        api_client.force_authenticate(user=professor_user)
        response = api_client.post(
            f"{add_event_url(match_obj.pk)}?academy={match_academy.pk}",
            {
                "athlete": match_obj.athlete_a_id,
                "event_type": "POINTS",
                "timestamp": 60,
                "points_awarded": 2,
                "action_description": "takedown",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_student_cannot_add_event(
        self, api_client, student_user, match_academy, match_obj
    ):
        api_client.force_authenticate(user=student_user)
        response = api_client.post(
            f"{add_event_url(match_obj.pk)}?academy={match_academy.pk}",
            {
                "athlete": match_obj.athlete_a_id,
                "event_type": "POINTS",
                "timestamp": 60,
                "points_awarded": 2,
                "action_description": "takedown",
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_add_event(self, api_client, match_academy, match_obj):
        response = api_client.post(
            f"{add_event_url(match_obj.pk)}?academy={match_academy.pk}",
            {
                "athlete": match_obj.athlete_a_id,
                "event_type": "POINTS",
                "timestamp": 60,
                "points_awarded": 2,
                "action_description": "takedown",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_participant_athlete_is_rejected(
        self, api_client, professor_user, match_academy, match_obj
    ):
        from factories import UserFactory
        outsider = UserFactory(username="non_participant")
        api_client.force_authenticate(user=professor_user)
        response = api_client.post(
            f"{add_event_url(match_obj.pk)}?academy={match_academy.pk}",
            {
                "athlete": outsider.pk,
                "event_type": "POINTS",
                "timestamp": 30,
                "points_awarded": 2,
                "action_description": "sweep",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_score_incremented_for_athlete_a_points_event(
        self, api_client, professor_user, match_academy, match_obj
    ):
        api_client.force_authenticate(user=professor_user)
        api_client.post(
            f"{add_event_url(match_obj.pk)}?academy={match_academy.pk}",
            {
                "athlete": match_obj.athlete_a_id,
                "event_type": "POINTS",
                "timestamp": 90,
                "points_awarded": 3,
                "action_description": "guard pass",
            },
        )
        match_obj.refresh_from_db()
        assert match_obj.score_a == 3
        assert match_obj.score_b == 0
