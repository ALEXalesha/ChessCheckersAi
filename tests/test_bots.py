"""Боты для проверок и турнир с зёрнами."""
from functools import partial

import numpy as np

from aikit import tournament
from game.ai import bots, games
from game.core import checkers as ck


def test_random_bot_plays_legal_moves_and_repeats_with_the_same_seed():
    def game_moves(seed):
        g = ck.Game()
        w = bots.RandomBot(np.random.default_rng(seed))
        b = bots.RandomBot(np.random.default_rng(seed + 1))
        bots.play(g, w, b, max_plies=60)
        return [ck.move_text(m) for m in g.moves]
    assert game_moves(1) == game_moves(1)
    assert game_moves(1) != game_moves(2)


def test_greedy_takes_the_most_pieces():
    g = ck.Game(ck.from_squares(white=["c3"], black=["b4", "d4", "f6"]))
    bot = games.make_player("checkers", {"kind": "greedy"}, np.random.default_rng(0))
    for _ in range(5):
        assert ck.move_text(bot.choose(g)) == "c3:e5:g7"


def test_greedy_moves_randomly_without_captures():
    g = ck.Game()
    bot = games.make_player("checkers", {"kind": "greedy"}, np.random.default_rng(0))
    assert len({ck.move_text(bot.choose(g)) for _ in range(40)}) > 3


def test_play_stops_at_the_limit_and_reports_the_result():
    g = ck.Game()
    rng = np.random.default_rng(0)
    res = bots.play(g, bots.RandomBot(rng), bots.RandomBot(rng), max_plies=10)
    assert res == (0, "limit", 10)
    g = ck.Game(ck.from_squares(white=["c3"], black=["d4"]))
    assert bots.play(g, bots.RandomBot(rng), bots.RandomBot(rng)) == (1, "no_pieces", 1)


def test_opening_plies_are_random_then_players_move():
    g = ck.Game()
    rng = np.random.default_rng(3)
    seen = []

    class Spy:
        def choose(self, game):
            seen.append(len(game.moves))
            return game.legal()[0]
    bots.play(g, Spy(), Spy(), rng, opening=3, max_plies=6)
    assert seen == [3, 4, 5]


def test_material_search_beats_random():
    play = partial(games.play_one, game="checkers", subject={"kind": "material", "depth": 2},
                   opponent={"kind": "random"})
    res = tournament.run(play, 8, seed=1)
    assert res.count("W") >= 7


def test_tournament_games_repeat_one_by_one():
    play = partial(games.play_one, game="checkers", subject={"kind": "material", "depth": 1},
                   opponent={"kind": "greedy"})
    full = tournament.run(play, 6, seed=9)
    assert tournament.run(play, 6, seed=9) == full
    assert tournament.run(play, 6, seed=9, indices=[4, 1]) == full[4] + full[1]


def test_tournament_in_processes_gives_the_same_games():
    play = partial(games.play_one, game="checkers", subject={"kind": "material", "depth": 1},
                   opponent={"kind": "random"})
    assert tournament.run(play, 4, seed=2, processes=2) == tournament.run(play, 4, seed=2)
