import pytest

from aikit import tournament


def coin(i, rng, first):
    x = rng.random()
    return "W" if x < 0.5 else ("D" if x < 0.7 else "L")


def test_each_game_has_its_own_seed_so_a_sample_matches_the_full_run():
    full = tournament.run(coin, 40, seed=5)
    sample = tournament.run(coin, 40, seed=5, indices=[3, 17, 39])
    assert sample == full[3] + full[17] + full[39]


def test_other_seed_gives_other_games():
    assert tournament.run(coin, 40, seed=5) != tournament.run(coin, 40, seed=6)


def test_colors_alternate():
    firsts = []
    tournament.run(lambda i, rng, f: firsts.append(f) or "D", 4, seed=0)
    assert firsts == [True, False, True, False]


def test_summary_counts():
    s = tournament.summary("WWDLW")
    assert (s["wins"], s["draws"], s["losses"], s["games"], s["score"]) == (3, 1, 1, 5, 0.7)


def test_bad_result_is_an_error():
    with pytest.raises(ValueError):
        tournament.run(lambda i, rng, f: "победа", 1, seed=0)


def test_ci95_shrinks_with_more_games_and_uses_rule_of_three_for_identical_results():
    assert tournament.ci95("W" * 50) == 3 / 50
    small = tournament.ci95("WDL" * 10)
    big = tournament.ci95("WDL" * 40)
    assert big < small and abs(small / big - 2.0) < 0.1     # в 4 раза больше партий - вдвое уже


def test_ci95_value_for_a_coin():
    # 100 партий, половина побед, половина поражений: 1.96 * sqrt(0.25 * 100/99 / 100) ~ 0.0985
    assert abs(tournament.ci95("WL" * 50) - 0.0985) < 0.001


def test_different_and_saturated():
    assert tournament.different("W" * 90 + "L" * 10, "W" * 50 + "L" * 50)
    assert not tournament.different("W" * 6 + "L" * 4, "W" * 5 + "L" * 5)
    assert tournament.saturated("WWW", "WW") and not tournament.saturated("WWD", "WW")
