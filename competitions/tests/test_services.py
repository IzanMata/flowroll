"""
Tests for TournamentService — full lifecycle: create, open, register,
withdraw, generate_bracket, record_match_result, complete.
"""

import datetime

import pytest

from competitions.models import Tournament, TournamentMatch, TournamentParticipant
from competitions.services import TournamentService
from factories import (
    AcademyFactory,
    AthleteProfileFactory,
    TournamentDivisionFactory,
    TournamentFactory,
    TournamentParticipantFactory,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def academy(db):
    return AcademyFactory()


@pytest.fixture
def open_tournament(academy):
    t = TournamentFactory(academy=academy, status="DRAFT", max_participants=None)
    return TournamentService.open_registration(t)


@pytest.fixture
def two_athletes(academy):
    a1 = AthleteProfileFactory(academy=academy, belt="blue", stripes=2, weight=70.0)
    a2 = AthleteProfileFactory(academy=academy, belt="white", stripes=0, weight=65.0)
    return a1, a2


# ─── create_tournament ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCreateTournament:
    def test_creates_in_draft_status(self, academy):
        t = TournamentService.create_tournament(
            academy=academy,
            name="Test Open",
            date=datetime.date(2025, 12, 1),
        )
        assert t.pk is not None
        assert t.status == Tournament.Status.DRAFT
        assert t.academy == academy

    def test_defaults_to_bracket_format(self, academy):
        t = TournamentService.create_tournament(
            academy=academy, name="X", date=datetime.date(2025, 12, 1)
        )
        assert t.format == Tournament.Format.BRACKET

    def test_stores_optional_fields(self, academy):
        t = TournamentService.create_tournament(
            academy=academy,
            name="Summer Cup",
            date=datetime.date(2025, 8, 1),
            description="Annual event",
            location="Rio de Janeiro",
            max_participants=32,
        )
        assert t.description == "Annual event"
        assert t.location == "Rio de Janeiro"
        assert t.max_participants == 32


# ─── open_registration ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestOpenRegistration:
    def test_draft_transitions_to_open(self, academy):
        t = TournamentFactory(academy=academy, status="DRAFT")
        result = TournamentService.open_registration(t)
        assert result.status == Tournament.Status.OPEN
        t.refresh_from_db()
        assert t.status == Tournament.Status.OPEN

    def test_non_draft_raises(self, open_tournament):
        with pytest.raises(ValueError, match="DRAFT"):
            TournamentService.open_registration(open_tournament)

    def test_completed_raises(self, academy):
        t = TournamentFactory(academy=academy, status="COMPLETED")
        with pytest.raises(ValueError):
            TournamentService.open_registration(t)


# ─── register_participant ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRegisterParticipant:
    def test_registers_athlete_with_confirmed_status(self, open_tournament, two_athletes):
        a1, _ = two_athletes
        p = TournamentService.register_participant(open_tournament, a1)
        assert p.status == TournamentParticipant.RegistrationStatus.CONFIRMED
        assert p.athlete == a1

    def test_snapshots_belt_at_registration_time(self, open_tournament, academy):
        athlete = AthleteProfileFactory(academy=academy, belt="purple", weight=80.0)
        p = TournamentService.register_participant(open_tournament, athlete)
        assert p.belt_at_registration == "purple"
        assert p.weight_at_registration == 80.0

    def test_raises_if_tournament_not_open(self, academy, two_athletes):
        draft = TournamentFactory(academy=academy, status="DRAFT")
        a1, _ = two_athletes
        with pytest.raises(ValueError, match="OPEN"):
            TournamentService.register_participant(draft, a1)

    def test_raises_if_already_registered(self, open_tournament, two_athletes):
        a1, _ = two_athletes
        TournamentService.register_participant(open_tournament, a1)
        with pytest.raises(ValueError, match="already registered"):
            TournamentService.register_participant(open_tournament, a1)

    def test_allows_re_registration_after_withdrawal(self, open_tournament, academy):
        athlete = AthleteProfileFactory(academy=academy)
        p = TournamentService.register_participant(open_tournament, athlete)
        TournamentService.withdraw_participant(p)
        p2 = TournamentService.register_participant(open_tournament, athlete)
        assert p2.status == TournamentParticipant.RegistrationStatus.CONFIRMED

    def test_raises_when_tournament_is_full(self, academy):
        t = TournamentFactory(academy=academy, status="OPEN", max_participants=1)
        a1 = AthleteProfileFactory(academy=academy)
        a2 = AthleteProfileFactory(academy=academy)
        TournamentService.register_participant(t, a1)
        with pytest.raises(ValueError, match="full"):
            TournamentService.register_participant(t, a2)

    def test_withdrawn_participant_not_counted_toward_capacity(self, academy):
        t = TournamentFactory(academy=academy, status="OPEN", max_participants=1)
        a1 = AthleteProfileFactory(academy=academy)
        a2 = AthleteProfileFactory(academy=academy)
        p1 = TournamentService.register_participant(t, a1)
        TournamentService.withdraw_participant(p1)
        # Slot freed, a2 should succeed
        p2 = TournamentService.register_participant(t, a2)
        assert p2.status == TournamentParticipant.RegistrationStatus.CONFIRMED

    def test_registers_with_division(self, open_tournament, academy):
        div = TournamentDivisionFactory(tournament=open_tournament)
        athlete = AthleteProfileFactory(academy=academy)
        p = TournamentService.register_participant(open_tournament, athlete, division=div)
        assert p.division == div


# ─── withdraw_participant ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestWithdrawParticipant:
    def test_sets_status_to_withdrawn(self, open_tournament, academy):
        athlete = AthleteProfileFactory(academy=academy)
        p = TournamentService.register_participant(open_tournament, athlete)
        result = TournamentService.withdraw_participant(p)
        assert result.status == TournamentParticipant.RegistrationStatus.WITHDRAWN

    def test_raises_if_already_withdrawn(self, open_tournament, academy):
        athlete = AthleteProfileFactory(academy=academy)
        p = TournamentService.register_participant(open_tournament, athlete)
        TournamentService.withdraw_participant(p)
        p.refresh_from_db()
        with pytest.raises(ValueError, match="already withdrawn"):
            TournamentService.withdraw_participant(p)


# ─── generate_bracket ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestGenerateBracket:
    def _register_n(self, tournament, n, belt="white", stripes=0, weight=70.0):
        athletes = []
        for i in range(n):
            a = AthleteProfileFactory(belt=belt, stripes=stripes, weight=weight + i)
            TournamentService.register_participant(tournament, a)
            athletes.append(a)
        return athletes

    def test_even_participants_creates_n_over_2_matches(self, open_tournament):
        self._register_n(open_tournament, 4)
        matches = TournamentService.generate_bracket(open_tournament)
        assert len(matches) == 2

    def test_odd_participants_gives_bye_to_top_seed(self, open_tournament):
        self._register_n(open_tournament, 3)
        matches = TournamentService.generate_bracket(open_tournament)
        # 3 athletes → 1 match (athlete 3 gets bye)
        assert len(matches) == 1

    def test_transitions_to_in_progress(self, open_tournament):
        self._register_n(open_tournament, 2)
        TournamentService.generate_bracket(open_tournament)
        open_tournament.refresh_from_db()
        assert open_tournament.status == Tournament.Status.IN_PROGRESS

    def test_raises_if_not_open(self, academy):
        draft = TournamentFactory(academy=academy, status="DRAFT")
        with pytest.raises(ValueError, match="OPEN"):
            TournamentService.generate_bracket(draft)

    def test_raises_if_fewer_than_2_participants(self, open_tournament, academy):
        athlete = AthleteProfileFactory(academy=academy)
        TournamentService.register_participant(open_tournament, athlete)
        with pytest.raises(ValueError, match="2 confirmed"):
            TournamentService.generate_bracket(open_tournament)

    def test_raises_if_no_participants(self, open_tournament):
        with pytest.raises(ValueError):
            TournamentService.generate_bracket(open_tournament)

    def test_seeds_assigned_to_participants(self, open_tournament):
        self._register_n(open_tournament, 4)
        TournamentService.generate_bracket(open_tournament)
        seeds = list(
            TournamentParticipant.objects.filter(tournament=open_tournament)
            .exclude(seed=None)
            .values_list("seed", flat=True)
        )
        assert sorted(seeds) == [1, 2, 3, 4]

    def test_higher_belt_gets_lower_seed_number(self, open_tournament, academy):
        """Seed 1 should be the highest belt (BLACK)."""
        white = AthleteProfileFactory(academy=academy, belt="white", stripes=0, weight=70.0)
        black = AthleteProfileFactory(academy=academy, belt="black", stripes=4, weight=70.0)
        TournamentService.register_participant(open_tournament, white)
        TournamentService.register_participant(open_tournament, black)
        TournamentService.generate_bracket(open_tournament)
        black_participant = TournamentParticipant.objects.get(
            tournament=open_tournament, athlete=black
        )
        assert black_participant.seed == 1

    def test_withdrawn_athletes_excluded_from_bracket(self, open_tournament, academy):
        a1 = AthleteProfileFactory(academy=academy)
        a2 = AthleteProfileFactory(academy=academy)
        a3 = AthleteProfileFactory(academy=academy)
        p1 = TournamentService.register_participant(open_tournament, a1)
        TournamentService.register_participant(open_tournament, a2)
        TournamentService.register_participant(open_tournament, a3)
        TournamentService.withdraw_participant(p1)
        # Only 2 confirmed remain
        matches = TournamentService.generate_bracket(open_tournament)
        assert len(matches) == 1

    def test_matches_are_round_1(self, open_tournament):
        self._register_n(open_tournament, 4)
        matches = TournamentService.generate_bracket(open_tournament)
        assert all(m.round_number == 1 for m in matches)

    def test_matches_persisted_in_db(self, open_tournament):
        self._register_n(open_tournament, 4)
        TournamentService.generate_bracket(open_tournament)
        assert TournamentMatch.objects.filter(tournament=open_tournament).count() == 2


# ─── record_match_result ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRecordMatchResult:
    @pytest.fixture
    def match_with_athletes(self, open_tournament, academy):
        a1 = AthleteProfileFactory(academy=academy)
        a2 = AthleteProfileFactory(academy=academy)
        TournamentService.register_participant(open_tournament, a1)
        TournamentService.register_participant(open_tournament, a2)
        (match,) = TournamentService.generate_bracket(open_tournament)
        return match, a1, a2

    def test_records_winner_and_scores(self, match_with_athletes):
        match, a1, a2 = match_with_athletes
        result = TournamentService.record_match_result(match, winner=a1, score_a=6, score_b=2)
        assert result.winner == a1
        assert result.score_a == 6
        assert result.score_b == 2
        assert result.is_finished is True

    def test_raises_if_match_already_finished(self, match_with_athletes):
        match, a1, a2 = match_with_athletes
        TournamentService.record_match_result(match, winner=a1)
        match.refresh_from_db()
        with pytest.raises(ValueError, match="already finished"):
            TournamentService.record_match_result(match, winner=a2)

    def test_raises_if_winner_not_a_participant(self, match_with_athletes, academy):
        match, a1, a2 = match_with_athletes
        stranger = AthleteProfileFactory(academy=academy)
        with pytest.raises(ValueError, match="Winner must be"):
            TournamentService.record_match_result(match, winner=stranger)

    def test_stores_notes(self, match_with_athletes):
        match, a1, _ = match_with_athletes
        result = TournamentService.record_match_result(match, winner=a1, notes="Won by armbar")
        assert result.notes == "Won by armbar"


# ─── complete_tournament ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCompleteTournament:
    def test_in_progress_transitions_to_completed(self, academy):
        t = TournamentFactory(academy=academy, status="IN_PROGRESS")
        result = TournamentService.complete_tournament(t)
        assert result.status == Tournament.Status.COMPLETED
        t.refresh_from_db()
        assert t.status == Tournament.Status.COMPLETED

    def test_raises_if_not_in_progress(self, academy):
        t = TournamentFactory(academy=academy, status="OPEN")
        with pytest.raises(ValueError, match="IN_PROGRESS"):
            TournamentService.complete_tournament(t)

    def test_raises_if_draft(self, academy):
        t = TournamentFactory(academy=academy, status="DRAFT")
        with pytest.raises(ValueError):
            TournamentService.complete_tournament(t)
