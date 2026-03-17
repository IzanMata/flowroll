"""
Unit tests for MatchmakingService.

Run with:  pytest tatami/tests/test_matchmaking.py
"""

import pytest

from tatami.models import Matchup, WeightClass
from tatami.services import BELT_ORDER, MatchmakingService, _athlete_score

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def weight_class(db):
    return WeightClass.objects.create(
        name="Middle", min_weight=64.0, max_weight=76.0, gender="O"
    )


# ---------------------------------------------------------------------------
# _athlete_score helper
# ---------------------------------------------------------------------------


class TestAthleteScore:
    def test_returns_tuple_of_belt_stripes_weight(self, make_athlete, belt_blue):
        athlete = make_athlete(belt=belt_blue, stripes=2, weight=70.0)
        score = _athlete_score(athlete)
        assert score == (BELT_ORDER["blue"], 2, 70.0)

    def test_missing_weight_defaults_to_zero(self, make_athlete, belt_white):
        athlete = make_athlete(belt=belt_white, stripes=0, weight=None)
        score = _athlete_score(athlete)
        assert score[2] == 0.0


# ---------------------------------------------------------------------------
# Tournament pairing
# ---------------------------------------------------------------------------


class TestTournamentPairing:
    def test_even_number_creates_correct_matchup_count(
        self, make_athlete, academy, belt_white
    ):
        athletes = [make_athlete(belt=belt_white) for _ in range(6)]
        matchups = MatchmakingService.pair_for_tournament(athletes, academy)
        assert len(matchups) == 3

    def test_odd_number_gives_one_bye(self, make_athlete, academy, belt_white):
        athletes = [make_athlete(belt=belt_white) for _ in range(5)]
        matchups = MatchmakingService.pair_for_tournament(athletes, academy)
        assert len(matchups) == 2  # one athlete receives a bye

    def test_single_athlete_produces_no_matchup(
        self, make_athlete, academy, belt_white
    ):
        athletes = [make_athlete(belt=belt_white)]
        matchups = MatchmakingService.pair_for_tournament(athletes, academy)
        assert matchups == []

    def test_matchups_persisted_to_db(self, make_athlete, academy, belt_white):
        athletes = [make_athlete(belt=belt_white) for _ in range(4)]
        MatchmakingService.pair_for_tournament(athletes, academy)
        assert (
            Matchup.objects.filter(
                match_format=Matchup.MatchFormat.TOURNAMENT, academy=academy
            ).count()
            == 2
        )

    def test_paired_by_nearest_belt(
        self, make_athlete, academy, belt_white, belt_blue, belt_purple
    ):
        """Athletes should be sorted by belt before pairing — closest skill levels face each other."""
        w1 = make_athlete(belt=belt_white, stripes=0)
        w2 = make_athlete(belt=belt_white, stripes=3)
        b1 = make_athlete(belt=belt_blue, stripes=0)
        b2 = make_athlete(belt=belt_blue, stripes=2)
        matchups = MatchmakingService.pair_for_tournament([w1, b1, w2, b2], academy)
        # After sorting: w1(0), w2(3), b1(0), b2(2) -> pairs: (w1,w2), (b1,b2)
        assert len(matchups) == 2
        pair_ids = {(m.athlete_a_id, m.athlete_b_id) for m in matchups}
        assert (w1.pk, w2.pk) in pair_ids
        assert (b1.pk, b2.pk) in pair_ids

    def test_weight_class_attached_to_matchup(
        self, make_athlete, academy, belt_white, weight_class
    ):
        athletes = [make_athlete(belt=belt_white) for _ in range(2)]
        matchups = MatchmakingService.pair_for_tournament(
            athletes, academy, weight_class=weight_class
        )
        assert matchups[0].weight_class == weight_class

    def test_round_number_stored(self, make_athlete, academy, belt_white):
        athletes = [make_athlete(belt=belt_white) for _ in range(2)]
        matchups = MatchmakingService.pair_for_tournament(
            athletes, academy, round_number=3
        )
        assert matchups[0].round_number == 3


# ---------------------------------------------------------------------------
# Survival (king-of-the-mat) pairing
# ---------------------------------------------------------------------------


class TestSurvivalPairing:
    def test_creates_single_matchup(self, make_athlete, academy, belt_blue):
        athletes = [make_athlete(belt=belt_blue) for _ in range(4)]
        matchups = MatchmakingService.pair_for_survival(athletes, academy)
        assert len(matchups) == 1

    def test_raises_with_fewer_than_two_athletes(
        self, make_athlete, academy, belt_white
    ):
        athletes = [make_athlete(belt=belt_white)]
        with pytest.raises(ValueError, match="at least 2"):
            MatchmakingService.pair_for_survival(athletes, academy)

    def test_highest_ranked_athlete_is_defender(
        self, make_athlete, academy, belt_white, belt_black
    ):
        white = make_athlete(belt=belt_white, stripes=0)
        black = make_athlete(belt=belt_black, stripes=0)
        matchups = MatchmakingService.pair_for_survival([white, black], academy)
        assert matchups[0].athlete_a == black  # black belt is defender (athlete_a)

    def test_match_format_is_survival(self, make_athlete, academy, belt_blue):
        athletes = [make_athlete(belt=belt_blue) for _ in range(2)]
        matchups = MatchmakingService.pair_for_survival(athletes, academy)
        assert matchups[0].match_format == Matchup.MatchFormat.SURVIVAL


# ---------------------------------------------------------------------------
# Survival advancement
# ---------------------------------------------------------------------------


class TestSurvivalAdvancement:
    def test_advance_creates_next_matchup(self, make_athlete, academy, belt_blue):
        a, b, c = [make_athlete(belt=belt_blue) for _ in range(3)]
        matchup = Matchup.objects.create(
            academy=academy,
            athlete_a=a,
            athlete_b=b,
            match_format=Matchup.MatchFormat.SURVIVAL,
            round_number=1,
            status=Matchup.MatchStatus.COMPLETED,
            winner=a,
        )
        next_matchup = MatchmakingService.advance_survival(
            matchup, remaining_challengers=[c]
        )
        assert next_matchup is not None
        assert next_matchup.athlete_a == a
        assert next_matchup.athlete_b == c
        assert next_matchup.round_number == 2

    def test_advance_returns_none_when_no_challengers(
        self, make_athlete, academy, belt_blue
    ):
        a, b = [make_athlete(belt=belt_blue) for _ in range(2)]
        matchup = Matchup.objects.create(
            academy=academy,
            athlete_a=a,
            athlete_b=b,
            match_format=Matchup.MatchFormat.SURVIVAL,
            round_number=1,
            status=Matchup.MatchStatus.COMPLETED,
            winner=a,
        )
        result = MatchmakingService.advance_survival(matchup, remaining_challengers=[])
        assert result is None

    def test_advance_raises_if_matchup_not_completed(
        self, make_athlete, academy, belt_blue
    ):
        a, b = [make_athlete(belt=belt_blue) for _ in range(2)]
        matchup = Matchup.objects.create(
            academy=academy,
            athlete_a=a,
            athlete_b=b,
            match_format=Matchup.MatchFormat.SURVIVAL,
            round_number=1,
            status=Matchup.MatchStatus.PENDING,
        )
        with pytest.raises(ValueError, match="not completed"):
            MatchmakingService.advance_survival(matchup, remaining_challengers=[b])


# ---------------------------------------------------------------------------
# Weight-class filtering
# ---------------------------------------------------------------------------


class TestWeightClassFiltering:
    def test_filters_athletes_within_range(self, make_athlete, weight_class):
        in_range = [make_athlete(weight=70.0), make_athlete(weight=64.0)]
        out_of_range = [make_athlete(weight=80.0), make_athlete(weight=50.0)]
        result = MatchmakingService.filter_by_weight_class(
            in_range + out_of_range, weight_class
        )
        assert set(result) == set(in_range)

    def test_excludes_athletes_with_no_weight(self, make_athlete, weight_class):
        athlete = make_athlete(weight=None)
        result = MatchmakingService.filter_by_weight_class([athlete], weight_class)
        assert result == []
