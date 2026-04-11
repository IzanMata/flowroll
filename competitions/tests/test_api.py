"""
API tests for the competitions app.

Covers: TournamentViewSet (CRUD + custom actions), TournamentDivisionViewSet,
TournamentMatchViewSet result action, and permission enforcement.
"""

import datetime

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from competitions.models import Tournament, TournamentParticipant
from competitions.services import TournamentService
from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    TournamentDivisionFactory,
    TournamentFactory,
    TournamentParticipantFactory,
    UserFactory,
)

TOURNAMENTS_URL = "/api/v1/competitions/tournaments/"
DIVISIONS_URL = "/api/v1/competitions/divisions/"
MATCHES_URL = "/api/v1/competitions/matches/"


def detail_url(pk):
    return f"{TOURNAMENTS_URL}{pk}/"


def action_url(pk, action):
    return f"{TOURNAMENTS_URL}{pk}/{action}/"


def match_result_url(pk):
    return f"{MATCHES_URL}{pk}/result/"


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def comp_academy(db):
    return AcademyFactory()


@pytest.fixture
def professor_user(comp_academy):
    user = UserFactory()
    AcademyMembershipFactory(user=user, academy=comp_academy, role="PROFESSOR", is_active=True)
    return user


@pytest.fixture
def student_user(comp_academy):
    user = UserFactory()
    AcademyMembershipFactory(user=user, academy=comp_academy, role="STUDENT", is_active=True)
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
def draft_tournament(comp_academy):
    return TournamentFactory(academy=comp_academy, status="DRAFT")


@pytest.fixture
def open_tournament(comp_academy):
    return TournamentFactory(academy=comp_academy, status="OPEN")


# ─── Auth guard ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTournamentAuthGuard:
    def test_unauthenticated_list_returns_401(self, anon_client, comp_academy):
        response = anon_client.get(f"{TOURNAMENTS_URL}?academy={comp_academy.pk}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unauthenticated_create_returns_401(self, anon_client, comp_academy):
        response = anon_client.post(
            f"{TOURNAMENTS_URL}?academy={comp_academy.pk}",
            {"name": "X", "date": "2025-12-01"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── Permission checks ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTournamentPermissions:
    def test_member_can_list_tournaments(self, student_client, comp_academy, draft_tournament):
        response = student_client.get(f"{TOURNAMENTS_URL}?academy={comp_academy.pk}")
        assert response.status_code == status.HTTP_200_OK

    def test_non_member_cannot_list(self, comp_academy, draft_tournament):
        outsider = UserFactory()
        client = APIClient()
        client.force_authenticate(user=outsider)
        response = client.get(f"{TOURNAMENTS_URL}?academy={comp_academy.pk}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_create_tournament(self, student_client, comp_academy):
        response = student_client.post(
            f"{TOURNAMENTS_URL}?academy={comp_academy.pk}",
            {"name": "Student Cup", "date": "2025-12-01"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_create_tournament(self, prof_client, comp_academy):
        response = prof_client.post(
            f"{TOURNAMENTS_URL}?academy={comp_academy.pk}",
            {"name": "Prof Cup", "date": "2025-12-01", "format": "BRACKET"},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_student_cannot_delete_tournament(self, student_client, comp_academy, draft_tournament):
        response = student_client.delete(
            f"{detail_url(draft_tournament.pk)}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ─── Queryset scoping ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTournamentScoping:
    def test_no_academy_param_returns_empty(self, prof_client):
        response = prof_client.get(TOURNAMENTS_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_only_own_academy_tournaments_visible(
        self, prof_client, comp_academy, draft_tournament
    ):
        other = AcademyFactory()
        TournamentFactory(academy=other)
        response = prof_client.get(f"{TOURNAMENTS_URL}?academy={comp_academy.pk}")
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == draft_tournament.pk

    def test_status_filter(self, prof_client, comp_academy):
        TournamentFactory(academy=comp_academy, status="DRAFT")
        TournamentFactory(academy=comp_academy, status="OPEN")
        response = prof_client.get(
            f"{TOURNAMENTS_URL}?academy={comp_academy.pk}&status=DRAFT"
        )
        assert response.data["count"] == 1
        assert response.data["results"][0]["status"] == "DRAFT"


# ─── CRUD ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTournamentCRUD:
    def test_retrieve_tournament(self, prof_client, comp_academy, draft_tournament):
        response = prof_client.get(
            f"{detail_url(draft_tournament.pk)}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == draft_tournament.name

    def test_update_tournament_name(self, prof_client, comp_academy, draft_tournament):
        response = prof_client.patch(
            f"{detail_url(draft_tournament.pk)}?academy={comp_academy.pk}",
            {"name": "Updated Name"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Updated Name"

    def test_delete_tournament(self, prof_client, comp_academy, draft_tournament):
        response = prof_client.delete(
            f"{detail_url(draft_tournament.pk)}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Tournament.objects.filter(pk=draft_tournament.pk).exists()


# ─── open action ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestOpenAction:
    def test_professor_can_open_draft(self, prof_client, comp_academy, draft_tournament):
        response = prof_client.post(
            f"{action_url(draft_tournament.pk, 'open')}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "OPEN"

    def test_student_cannot_open(self, student_client, comp_academy, draft_tournament):
        response = student_client.post(
            f"{action_url(draft_tournament.pk, 'open')}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_opening_non_draft_returns_400(self, prof_client, comp_academy, open_tournament):
        response = prof_client.post(
            f"{action_url(open_tournament.pk, 'open')}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ─── register action ──────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRegisterAction:
    def test_professor_can_register_athlete(
        self, prof_client, comp_academy, open_tournament
    ):
        athlete = AthleteProfileFactory(academy=comp_academy)
        response = prof_client.post(
            f"{action_url(open_tournament.pk, 'register')}?academy={comp_academy.pk}",
            {"athlete_id": athlete.pk},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "CONFIRMED"

    def test_register_with_division(self, prof_client, comp_academy, open_tournament):
        athlete = AthleteProfileFactory(academy=comp_academy)
        div = TournamentDivisionFactory(tournament=open_tournament)
        response = prof_client.post(
            f"{action_url(open_tournament.pk, 'register')}?academy={comp_academy.pk}",
            {"athlete_id": athlete.pk, "division_id": div.pk},
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_student_cannot_register_athlete(
        self, student_client, comp_academy, open_tournament
    ):
        athlete = AthleteProfileFactory(academy=comp_academy)
        response = student_client.post(
            f"{action_url(open_tournament.pk, 'register')}?academy={comp_academy.pk}",
            {"athlete_id": athlete.pk},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_registration_returns_400(
        self, prof_client, comp_academy, open_tournament
    ):
        athlete = AthleteProfileFactory(academy=comp_academy)
        prof_client.post(
            f"{action_url(open_tournament.pk, 'register')}?academy={comp_academy.pk}",
            {"athlete_id": athlete.pk},
        )
        response = prof_client.post(
            f"{action_url(open_tournament.pk, 'register')}?academy={comp_academy.pk}",
            {"athlete_id": athlete.pk},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ─── generate_bracket action ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestGenerateBracketAction:
    def _register(self, tournament, n=2):
        athletes = []
        for _ in range(n):
            a = AthleteProfileFactory()
            TournamentService.register_participant(tournament, a)
            athletes.append(a)
        return athletes

    def test_professor_generates_bracket(self, prof_client, comp_academy, open_tournament):
        self._register(open_tournament, 2)
        response = prof_client.post(
            f"{action_url(open_tournament.pk, 'generate_bracket')}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data) == 1  # 2 athletes → 1 match

    def test_student_cannot_generate_bracket(self, student_client, comp_academy, open_tournament):
        self._register(open_tournament, 2)
        response = student_client.post(
            f"{action_url(open_tournament.pk, 'generate_bracket')}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_fewer_than_2_returns_400(self, prof_client, comp_academy, open_tournament):
        AthleteProfileFactory()  # not registered
        response = prof_client.post(
            f"{action_url(open_tournament.pk, 'generate_bracket')}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ─── bracket action (GET) ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestBracketAction:
    def test_member_can_view_bracket(self, student_client, comp_academy, open_tournament):
        a1 = AthleteProfileFactory()
        a2 = AthleteProfileFactory()
        TournamentService.register_participant(open_tournament, a1)
        TournamentService.register_participant(open_tournament, a2)
        TournamentService.generate_bracket(open_tournament)
        response = student_client.get(
            f"{action_url(open_tournament.pk, 'bracket')}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_empty_bracket_returns_empty_list(
        self, student_client, comp_academy, open_tournament
    ):
        response = student_client.get(
            f"{action_url(open_tournament.pk, 'bracket')}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []


# ─── participants action (GET) ────────────────────────────────────────────────


@pytest.mark.django_db
class TestParticipantsAction:
    def test_lists_confirmed_participants(
        self, student_client, comp_academy, open_tournament
    ):
        a1 = AthleteProfileFactory()
        a2 = AthleteProfileFactory()
        TournamentService.register_participant(open_tournament, a1)
        TournamentService.register_participant(open_tournament, a2)
        response = student_client.get(
            f"{action_url(open_tournament.pk, 'participants')}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_withdrawn_not_included(self, student_client, comp_academy, open_tournament):
        a1 = AthleteProfileFactory()
        a2 = AthleteProfileFactory()
        p1 = TournamentService.register_participant(open_tournament, a1)
        TournamentService.register_participant(open_tournament, a2)
        TournamentService.withdraw_participant(p1)
        response = student_client.get(
            f"{action_url(open_tournament.pk, 'participants')}?academy={comp_academy.pk}"
        )
        assert len(response.data) == 1


# ─── complete action ──────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCompleteAction:
    def test_professor_can_complete_in_progress(self, prof_client, comp_academy):
        t = TournamentFactory(academy=comp_academy, status="IN_PROGRESS")
        response = prof_client.post(
            f"{action_url(t.pk, 'complete')}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "COMPLETED"

    def test_completing_non_in_progress_returns_400(
        self, prof_client, comp_academy, open_tournament
    ):
        response = prof_client.post(
            f"{action_url(open_tournament.pk, 'complete')}?academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ─── TournamentMatch result action ────────────────────────────────────────────


@pytest.mark.django_db
class TestMatchResultAction:
    @pytest.fixture
    def in_progress_data(self, comp_academy):
        t = TournamentFactory(academy=comp_academy, status="OPEN")
        a1 = AthleteProfileFactory(academy=comp_academy)
        a2 = AthleteProfileFactory(academy=comp_academy)
        TournamentService.register_participant(t, a1)
        TournamentService.register_participant(t, a2)
        (match,) = TournamentService.generate_bracket(t)
        return t, match, a1, a2

    def test_professor_can_record_result(
        self, prof_client, comp_academy, in_progress_data
    ):
        t, match, a1, a2 = in_progress_data
        response = prof_client.post(
            f"{match_result_url(match.pk)}?academy={comp_academy.pk}",
            {"winner_id": a1.pk, "score_a": 4, "score_b": 0, "notes": ""},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_finished"] is True

    def test_invalid_winner_returns_400(
        self, prof_client, comp_academy, in_progress_data
    ):
        t, match, a1, a2 = in_progress_data
        stranger = AthleteProfileFactory()
        response = prof_client.post(
            f"{match_result_url(match.pk)}?academy={comp_academy.pk}",
            {"winner_id": stranger.pk, "score_a": 0, "score_b": 0, "notes": ""},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_recording_already_finished_match_returns_400(
        self, prof_client, comp_academy, in_progress_data
    ):
        t, match, a1, a2 = in_progress_data
        prof_client.post(
            f"{match_result_url(match.pk)}?academy={comp_academy.pk}",
            {"winner_id": a1.pk, "score_a": 2, "score_b": 0, "notes": ""},
        )
        response = prof_client.post(
            f"{match_result_url(match.pk)}?academy={comp_academy.pk}",
            {"winner_id": a2.pk, "score_a": 0, "score_b": 4, "notes": ""},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ─── TournamentDivisionViewSet ────────────────────────────────────────────────


@pytest.mark.django_db
class TestDivisionViewSet:
    def test_professor_can_create_division(self, prof_client, comp_academy, open_tournament):
        response = prof_client.post(
            f"{DIVISIONS_URL}?tournament={open_tournament.pk}&academy={comp_academy.pk}",
            {
                "name": "White Belt Open",
                "belt_min": "white",
                "belt_max": "white",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_member_can_list_divisions(self, student_client, comp_academy, open_tournament):
        TournamentDivisionFactory(tournament=open_tournament)
        response = student_client.get(
            f"{DIVISIONS_URL}?tournament={open_tournament.pk}&academy={comp_academy.pk}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_no_tournament_no_academy_returns_403(self, student_client):
        # IsAcademyMember requires ?academy= param — absent means 403.
        response = student_client.get(DIVISIONS_URL)
        assert response.status_code == status.HTTP_403_FORBIDDEN
