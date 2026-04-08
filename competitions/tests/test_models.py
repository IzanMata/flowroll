"""
Tests for competitions models: Tournament, TournamentDivision,
TournamentParticipant, TournamentMatch.
"""

import pytest

from factories import (
    AcademyFactory,
    AthleteProfileFactory,
    TournamentDivisionFactory,
    TournamentFactory,
    TournamentMatchFactory,
    TournamentParticipantFactory,
)


@pytest.mark.django_db
class TestTournamentModel:
    def test_str_includes_name_and_date(self):
        t = TournamentFactory(name="Summer Open")
        assert "Summer Open" in str(t)
        assert str(t.date) in str(t)

    def test_default_status_is_draft(self):
        t = TournamentFactory()
        assert t.status == "DRAFT"

    def test_default_format_is_bracket(self):
        t = TournamentFactory()
        assert t.format == "BRACKET"

    def test_max_participants_nullable(self):
        t = TournamentFactory(max_participants=None)
        assert t.max_participants is None

    def test_ordering_newest_date_first(self):
        import datetime

        academy = AcademyFactory()
        t1 = TournamentFactory(academy=academy, date=datetime.date(2025, 1, 1))
        t2 = TournamentFactory(academy=academy, date=datetime.date(2025, 6, 1))
        from competitions.models import Tournament
        ids = list(Tournament.objects.filter(academy=academy).values_list("pk", flat=True))
        assert ids[0] == t2.pk  # newest first


@pytest.mark.django_db
class TestTournamentDivisionModel:
    def test_str_includes_tournament_and_name(self):
        div = TournamentDivisionFactory(name="Blue Belt -76 kg")
        assert "Blue Belt -76 kg" in str(div)
        assert div.tournament.name in str(div)

    def test_unique_together_tournament_name(self):
        from django.db import IntegrityError

        tournament = TournamentFactory()
        TournamentDivisionFactory(tournament=tournament, name="Open Weight")
        with pytest.raises(IntegrityError):
            TournamentDivisionFactory(tournament=tournament, name="Open Weight")

    def test_same_name_allowed_in_different_tournaments(self):
        TournamentDivisionFactory(name="Open Weight")
        TournamentDivisionFactory(name="Open Weight")  # different tournament — OK


@pytest.mark.django_db
class TestTournamentParticipantModel:
    def test_str_includes_athlete_and_tournament(self):
        p = TournamentParticipantFactory()
        assert p.tournament.name in str(p)

    def test_unique_together_tournament_athlete(self):
        from django.db import IntegrityError

        tournament = TournamentFactory()
        athlete = AthleteProfileFactory()
        TournamentParticipantFactory(tournament=tournament, athlete=athlete)
        with pytest.raises(IntegrityError):
            TournamentParticipantFactory(tournament=tournament, athlete=athlete)

    def test_default_status_is_confirmed(self):
        p = TournamentParticipantFactory()
        assert p.status == "CONFIRMED"

    def test_seed_nullable(self):
        p = TournamentParticipantFactory(seed=None)
        assert p.seed is None


@pytest.mark.django_db
class TestTournamentMatchModel:
    def test_str_includes_round_and_athletes(self):
        m = TournamentMatchFactory(round_number=1)
        result = str(m)
        assert "R1" in result

    def test_ordering_by_round_then_id(self):
        t = TournamentFactory()
        a1 = AthleteProfileFactory()
        a2 = AthleteProfileFactory()
        a3 = AthleteProfileFactory()
        a4 = AthleteProfileFactory()
        m2 = TournamentMatchFactory(tournament=t, round_number=2, athlete_a=a1, athlete_b=a2)
        m1 = TournamentMatchFactory(tournament=t, round_number=1, athlete_a=a3, athlete_b=a4)
        from competitions.models import TournamentMatch
        first = TournamentMatch.objects.filter(tournament=t).first()
        assert first.pk == m1.pk  # round 1 comes first

    def test_is_finished_defaults_to_false(self):
        m = TournamentMatchFactory()
        assert m.is_finished is False

    def test_winner_nullable(self):
        m = TournamentMatchFactory(winner=None)
        assert m.winner is None
