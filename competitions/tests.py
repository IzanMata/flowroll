"""
Tests for the competitions app: models, services, and API endpoints.

Covers:
  - Tournament, TournamentDivision, TournamentParticipant, TournamentMatch models
  - TournamentService lifecycle: create → open → register → bracket → results → complete
  - TournamentViewSet permission and action tests
"""

import pytest
from django.db import IntegrityError
from rest_framework import status

from competitions.models import (
    Tournament,
    TournamentDivision,
    TournamentMatch,
    TournamentParticipant,
)
from competitions.services import TournamentService
from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    TournamentDivisionFactory,
    TournamentFactory,
    TournamentMatchFactory,
    TournamentParticipantFactory,
    UserFactory,
)

TOURNAMENTS_URL = "/api/v1/competitions/tournaments/"


def tournament_url(pk, action=""):
    base = f"{TOURNAMENTS_URL}{pk}/"
    return f"{base}{action}/" if action else base


# ─── Model tests ──────────────────────────────────────────────────────────────


class TestTournamentModel:
    def test_create_tournament(self, db, academy):
        t = TournamentFactory(academy=academy, name="Spring Open")
        assert t.pk is not None
        assert t.status == Tournament.Status.DRAFT
        assert "Spring Open" in str(t)

    def test_default_status_is_draft(self, db, academy):
        t = TournamentFactory(academy=academy)
        assert t.status == Tournament.Status.DRAFT

    def test_default_format_is_bracket(self, db, academy):
        t = TournamentFactory(academy=academy)
        assert t.format == Tournament.Format.BRACKET

    def test_str_includes_name_and_date(self, db, academy):
        from datetime import date
        t = TournamentFactory(academy=academy, name="Summer Cup", date=date(2026, 6, 1))
        assert "Summer Cup" in str(t)
        assert "2026-06-01" in str(t)


class TestTournamentDivisionModel:
    def test_create_division(self, db):
        t = TournamentFactory()
        d = TournamentDivisionFactory(tournament=t, name="White Belt Open")
        assert d.pk is not None
        assert t.name in str(d)
        assert "White Belt Open" in str(d)

    def test_division_unique_per_tournament(self, db):
        t = TournamentFactory()
        TournamentDivisionFactory(tournament=t, name="Rooster")
        with pytest.raises(IntegrityError):
            TournamentDivisionFactory(tournament=t, name="Rooster")


class TestTournamentParticipantModel:
    def test_create_participant(self, db):
        t = TournamentFactory()
        athlete = AthleteProfileFactory()
        p = TournamentParticipantFactory(tournament=t, athlete=athlete, status="CONFIRMED")
        assert p.pk is not None
        assert str(athlete) in str(p)

    def test_unique_per_tournament(self, db):
        t = TournamentFactory()
        athlete = AthleteProfileFactory()
        TournamentParticipantFactory(tournament=t, athlete=athlete)
        with pytest.raises(IntegrityError):
            TournamentParticipantFactory(tournament=t, athlete=athlete)


class TestTournamentMatchModel:
    def test_create_match(self, db):
        t = TournamentFactory()
        a = AthleteProfileFactory()
        b = AthleteProfileFactory()
        m = TournamentMatchFactory(tournament=t, athlete_a=a, athlete_b=b)
        assert m.pk is not None
        assert m.is_finished is False
        assert m.score_a == 0
        assert m.score_b == 0


# ─── Service tests ────────────────────────────────────────────────────────────


class TestTournamentServiceCreate:
    def test_create_tournament_returns_draft(self, db, academy):
        from datetime import date
        t = TournamentService.create_tournament(
            academy=academy,
            name="Invitational",
            date=date(2026, 8, 1),
        )
        assert t.pk is not None
        assert t.status == Tournament.Status.DRAFT
        assert t.academy == academy

    def test_open_registration_transitions_to_open(self, db, academy):
        t = TournamentFactory(academy=academy, status="DRAFT")
        t = TournamentService.open_registration(t)
        assert t.status == Tournament.Status.OPEN

    def test_open_registration_fails_if_not_draft(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        with pytest.raises(ValueError, match="DRAFT"):
            TournamentService.open_registration(t)


class TestTournamentServiceRegister:
    def test_register_participant_confirms(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        athlete = AthleteProfileFactory(academy=academy)
        p = TournamentService.register_participant(t, athlete)
        assert p.status == TournamentParticipant.RegistrationStatus.CONFIRMED
        assert p.belt_at_registration == athlete.belt
        assert p.weight_at_registration == athlete.weight

    def test_register_with_division(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        div = TournamentDivisionFactory(tournament=t)
        athlete = AthleteProfileFactory(academy=academy)
        p = TournamentService.register_participant(t, athlete, division=div)
        assert p.division == div

    def test_register_fails_if_tournament_not_open(self, db, academy):
        t = TournamentFactory(academy=academy, status="DRAFT")
        athlete = AthleteProfileFactory(academy=academy)
        with pytest.raises(ValueError, match="OPEN"):
            TournamentService.register_participant(t, athlete)

    def test_register_fails_if_already_registered(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        athlete = AthleteProfileFactory(academy=academy)
        TournamentService.register_participant(t, athlete)
        with pytest.raises(ValueError, match="already registered"):
            TournamentService.register_participant(t, athlete)

    def test_register_fails_when_full(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN", max_participants=1)
        a1 = AthleteProfileFactory(academy=academy)
        a2 = AthleteProfileFactory(academy=academy)
        TournamentService.register_participant(t, a1)
        with pytest.raises(ValueError, match="full"):
            TournamentService.register_participant(t, a2)

    def test_withdraw_participant(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        athlete = AthleteProfileFactory(academy=academy)
        p = TournamentService.register_participant(t, athlete)
        p = TournamentService.withdraw_participant(p)
        assert p.status == TournamentParticipant.RegistrationStatus.WITHDRAWN

    def test_withdraw_already_withdrawn_fails(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        athlete = AthleteProfileFactory(academy=academy)
        p = TournamentParticipantFactory(tournament=t, athlete=athlete, status="WITHDRAWN")
        with pytest.raises(ValueError, match="already withdrawn"):
            TournamentService.withdraw_participant(p)

    def test_re_register_withdrawn_participant(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        athlete = AthleteProfileFactory(academy=academy)
        p = TournamentService.register_participant(t, athlete)
        TournamentService.withdraw_participant(p)
        p2 = TournamentService.register_participant(t, athlete)
        assert p2.status == TournamentParticipant.RegistrationStatus.CONFIRMED


class TestTournamentServiceBracket:
    def test_generate_bracket_creates_matches(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        athletes = [AthleteProfileFactory(academy=academy) for _ in range(4)]
        for a in athletes:
            TournamentService.register_participant(t, a)
        matches = TournamentService.generate_bracket(t)
        assert len(matches) == 2
        t.refresh_from_db()
        assert t.status == Tournament.Status.IN_PROGRESS

    def test_generate_bracket_with_odd_number_gives_bye(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        athletes = [AthleteProfileFactory(academy=academy) for _ in range(3)]
        for a in athletes:
            TournamentService.register_participant(t, a)
        matches = TournamentService.generate_bracket(t)
        assert len(matches) == 1

    def test_generate_bracket_fails_if_not_open(self, db, academy):
        t = TournamentFactory(academy=academy, status="DRAFT")
        with pytest.raises(ValueError, match="OPEN"):
            TournamentService.generate_bracket(t)

    def test_generate_bracket_fails_with_fewer_than_2_participants(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        a = AthleteProfileFactory(academy=academy)
        TournamentService.register_participant(t, a)
        with pytest.raises(ValueError, match="2 confirmed"):
            TournamentService.generate_bracket(t)

    def test_bracket_assigns_seeds(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        athletes = [AthleteProfileFactory(academy=academy) for _ in range(4)]
        for a in athletes:
            TournamentService.register_participant(t, a)
        TournamentService.generate_bracket(t)
        seeded = TournamentParticipant.objects.filter(tournament=t).exclude(seed=None)
        assert seeded.count() == 4

    def test_bracket_matches_persist_in_db(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        athletes = [AthleteProfileFactory(academy=academy) for _ in range(4)]
        for a in athletes:
            TournamentService.register_participant(t, a)
        TournamentService.generate_bracket(t)
        assert TournamentMatch.objects.filter(tournament=t, round_number=1).count() == 2


class TestTournamentServiceRecordResult:
    def test_record_result_finishes_match(self, db, academy):
        t = TournamentFactory(academy=academy, status="IN_PROGRESS")
        a = AthleteProfileFactory(academy=academy)
        b = AthleteProfileFactory(academy=academy)
        match = TournamentMatchFactory(tournament=t, athlete_a=a, athlete_b=b)
        match = TournamentService.record_match_result(match, winner=a, score_a=4, score_b=0)
        assert match.is_finished is True
        assert match.winner == a
        assert match.score_a == 4

    def test_record_result_fails_if_already_finished(self, db, academy):
        t = TournamentFactory(academy=academy, status="IN_PROGRESS")
        a = AthleteProfileFactory(academy=academy)
        b = AthleteProfileFactory(academy=academy)
        match = TournamentMatchFactory(tournament=t, athlete_a=a, athlete_b=b, is_finished=True, winner=a)
        with pytest.raises(ValueError, match="already finished"):
            TournamentService.record_match_result(match, winner=b)

    def test_record_result_rejects_non_participant_winner(self, db, academy):
        t = TournamentFactory(academy=academy, status="IN_PROGRESS")
        a = AthleteProfileFactory(academy=academy)
        b = AthleteProfileFactory(academy=academy)
        outsider = AthleteProfileFactory(academy=academy)
        match = TournamentMatchFactory(tournament=t, athlete_a=a, athlete_b=b)
        with pytest.raises(ValueError, match="participants"):
            TournamentService.record_match_result(match, winner=outsider)

    def test_record_result_saves_notes(self, db, academy):
        t = TournamentFactory(academy=academy, status="IN_PROGRESS")
        a = AthleteProfileFactory(academy=academy)
        b = AthleteProfileFactory(academy=academy)
        match = TournamentMatchFactory(tournament=t, athlete_a=a, athlete_b=b)
        match = TournamentService.record_match_result(match, winner=a, notes="Won by armbar")
        assert match.notes == "Won by armbar"


class TestTournamentServiceComplete:
    def test_complete_tournament(self, db, academy):
        t = TournamentFactory(academy=academy, status="IN_PROGRESS")
        t = TournamentService.complete_tournament(t)
        assert t.status == Tournament.Status.COMPLETED

    def test_complete_fails_if_not_in_progress(self, db, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        with pytest.raises(ValueError, match="IN_PROGRESS"):
            TournamentService.complete_tournament(t)


# ─── API tests ────────────────────────────────────────────────────────────────


@pytest.fixture
def comp_academy(db):
    return AcademyFactory(name="Comp Academy")


@pytest.fixture
def professor_user(db, comp_academy):
    user = UserFactory(username="comp_prof")
    AcademyMembershipFactory(user=user, academy=comp_academy, role="PROFESSOR", is_active=True)
    return user


@pytest.fixture
def student_user(db, comp_academy):
    user = UserFactory(username="comp_student")
    AcademyMembershipFactory(user=user, academy=comp_academy, role="STUDENT", is_active=True)
    return user


@pytest.fixture
def open_tournament(db, comp_academy):
    return TournamentFactory(academy=comp_academy, status="OPEN")


class TestTournamentAPIAuth:
    def test_unauthenticated_returns_401(self, api_client, comp_academy):
        r = api_client.get(f"{TOURNAMENTS_URL}?academy={comp_academy.pk}")
        assert r.status_code == status.HTTP_401_UNAUTHORIZED


class TestTournamentAPIPermissions:
    def test_student_can_list(self, api_client, student_user, comp_academy):
        api_client.force_authenticate(user=student_user)
        r = api_client.get(f"{TOURNAMENTS_URL}?academy={comp_academy.pk}")
        assert r.status_code == status.HTTP_200_OK

    def test_non_member_cannot_list(self, api_client, comp_academy):
        outsider = UserFactory()
        api_client.force_authenticate(user=outsider)
        r = api_client.get(f"{TOURNAMENTS_URL}?academy={comp_academy.pk}")
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_create_tournament(self, api_client, student_user, comp_academy):
        api_client.force_authenticate(user=student_user)
        r = api_client.post(
            f"{TOURNAMENTS_URL}?academy={comp_academy.pk}",
            {"name": "Test", "date": "2026-09-01", "format": "BRACKET"},
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_create_tournament(self, api_client, professor_user, comp_academy):
        api_client.force_authenticate(user=professor_user)
        r = api_client.post(
            f"{TOURNAMENTS_URL}?academy={comp_academy.pk}",
            {"name": "Prof Open", "date": "2026-09-01", "format": "BRACKET"},
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.data["status"] == "DRAFT"

    def test_no_academy_param_returns_empty(self, api_client, professor_user):
        api_client.force_authenticate(user=professor_user)
        r = api_client.get(TOURNAMENTS_URL)
        assert r.status_code == status.HTTP_200_OK
        assert r.data["count"] == 0


class TestTournamentAPIActions:
    def test_open_action_transitions_to_open(self, api_client, professor_user, comp_academy):
        t = TournamentFactory(academy=comp_academy, status="DRAFT")
        api_client.force_authenticate(user=professor_user)
        r = api_client.post(f"{tournament_url(t.pk, 'open')}?academy={comp_academy.pk}")
        assert r.status_code == status.HTTP_200_OK
        t.refresh_from_db()
        assert t.status == "OPEN"

    def test_open_action_fails_for_student(self, api_client, student_user, comp_academy):
        t = TournamentFactory(academy=comp_academy, status="DRAFT")
        api_client.force_authenticate(user=student_user)
        r = api_client.post(f"{tournament_url(t.pk, 'open')}?academy={comp_academy.pk}")
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_register_action_creates_participant(self, api_client, student_user, comp_academy, open_tournament):
        athlete = AthleteProfileFactory(academy=comp_academy, user=student_user)
        api_client.force_authenticate(user=student_user)
        r = api_client.post(
            f"{tournament_url(open_tournament.pk, 'register')}?academy={comp_academy.pk}",
            {"athlete_id": athlete.pk},
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert TournamentParticipant.objects.filter(
            tournament=open_tournament, athlete=athlete
        ).exists()

    def test_register_returns_400_for_closed_tournament(self, api_client, student_user, comp_academy):
        t = TournamentFactory(academy=comp_academy, status="IN_PROGRESS")
        athlete = AthleteProfileFactory(academy=comp_academy, user=student_user)
        api_client.force_authenticate(user=student_user)
        r = api_client.post(
            f"{tournament_url(t.pk, 'register')}?academy={comp_academy.pk}",
            {"athlete_id": athlete.pk},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_generate_bracket_creates_matches(self, api_client, professor_user, comp_academy, open_tournament):
        athletes = [AthleteProfileFactory(academy=comp_academy) for _ in range(4)]
        for a in athletes:
            TournamentParticipantFactory(tournament=open_tournament, athlete=a, status="CONFIRMED")
        api_client.force_authenticate(user=professor_user)
        r = api_client.post(
            f"{tournament_url(open_tournament.pk, 'generate_bracket')}?academy={comp_academy.pk}"
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert len(r.data) == 2

    def test_bracket_list_returns_matches(self, api_client, student_user, comp_academy):
        t = TournamentFactory(academy=comp_academy, status="IN_PROGRESS")
        a1 = AthleteProfileFactory(academy=comp_academy)
        a2 = AthleteProfileFactory(academy=comp_academy)
        TournamentMatchFactory(tournament=t, athlete_a=a1, athlete_b=a2)
        api_client.force_authenticate(user=student_user)
        r = api_client.get(f"{tournament_url(t.pk, 'bracket')}?academy={comp_academy.pk}")
        assert r.status_code == status.HTTP_200_OK
        assert len(r.data) >= 1

    def test_participants_list_returns_registered(self, api_client, student_user, comp_academy, open_tournament):
        athlete = AthleteProfileFactory(academy=comp_academy)
        TournamentParticipantFactory(tournament=open_tournament, athlete=athlete)
        api_client.force_authenticate(user=student_user)
        r = api_client.get(
            f"{tournament_url(open_tournament.pk, 'participants')}?academy={comp_academy.pk}"
        )
        assert r.status_code == status.HTTP_200_OK

    def test_complete_action(self, api_client, professor_user, comp_academy):
        t = TournamentFactory(academy=comp_academy, status="IN_PROGRESS")
        api_client.force_authenticate(user=professor_user)
        r = api_client.post(f"{tournament_url(t.pk, 'complete')}?academy={comp_academy.pk}")
        assert r.status_code == status.HTTP_200_OK
        t.refresh_from_db()
        assert t.status == "COMPLETED"

    def test_complete_returns_400_if_not_in_progress(self, api_client, professor_user, comp_academy):
        t = TournamentFactory(academy=comp_academy, status="OPEN")
        api_client.force_authenticate(user=professor_user)
        r = api_client.post(f"{tournament_url(t.pk, 'complete')}?academy={comp_academy.pk}")
        assert r.status_code == status.HTTP_400_BAD_REQUEST
