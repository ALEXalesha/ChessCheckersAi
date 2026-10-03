"""Шахматы в поиске: мат в один и два хода, тихий поиск не отдаёт ферзя, книга, вход сети."""
import random

import numpy as np
import pytest

from game.ai import chess_adapter as ca
from game.ai import games, net
from game.ai.search import MATE, Searcher
from game.core import chess as c


def best(fen, depth, quiescence=True):
    pos = c.from_fen(fen)
    r = Searcher(ca.CHESS, ca.chess_material, quiescence=quiescence).search(pos, depth=depth)
    return c.san(pos, r.move), r.score


def test_mate_in_one():
    move, score = best("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", 2)
    assert move == "Ra8#" and score > MATE - 1


def test_mate_in_two_with_a_sacrifice():
    # мат Легаля: 1. Nf6+ gxf6 2. Bxf7#
    move, score = best("r2qkb1r/pp2nppp/3p4/2pNN1B1/2BnP3/3P4/PPP2PPP/R2bK2R w KQkq - 1 1", 4)
    assert move == "Nf6+" and score > MATE - 1


def test_quiescence_does_not_take_a_defended_pawn_with_the_queen():
    fen = "4k3/8/4p3/3p4/8/8/8/3QK3 w - - 0 1"
    assert best(fen, 1, quiescence=False)[0] == "Qxd5"        # без тихого поиска - зевок
    assert best(fen, 1)[0] != "Qxd5"


def test_stalemate_scores_zero_and_mate_minus():
    assert ca.CHESS.no_moves_score(c.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")) == 0.0
    assert ca.CHESS.no_moves_score(c.from_fen("6Qk/8/6K1/8/8/8/8/8 b - - 0 1")) == -MATE


def test_mvv_lva_prefers_the_biggest_victim():
    pos = c.from_fen("4k3/8/8/2q1p3/3P4/8/8/4K3 w - - 0 1")
    caps = sorted(c.legal_captures(pos), key=lambda m: -ca.CHESS.order_key(pos, m))
    assert c.san(pos, caps[0]) == "dxc5"


def test_greedy_takes_the_queen_not_the_pawn():
    g = c.Game(c.from_fen("4k3/8/8/2q1p3/3P4/8/8/4K3 w - - 0 1"))
    bot = games.make_player("chess", {"kind": "greedy"}, np.random.default_rng(0))
    assert c.san(g.pos, bot.choose(g)) == "dxc5"


def test_book_has_the_usual_first_moves():
    first = {c.san(c.start(), m) for m in ca.book_moves(c.start())}
    assert {"e4", "d4", "c4", "Nf3"} <= first
    for line in ca.BOOK_LINES:                 # каждая строка книги - законные ходы
        g = c.Game()
        for s in line.split():
            g.push_san(s)


def mirrored(pos):
    """Та же позиция с другой стороны: доска по вертикали, цвета и очередь наоборот."""
    board, castle, ep = c.to_fen(pos).split()[0], c.to_fen(pos).split()[2], c.to_fen(pos).split()[3]
    rows = board.split("/")[::-1]
    board = "/".join(r.swapcase() for r in rows)
    castle = "".join(sorted(castle.swapcase(), key="KQkq".index)) if castle != "-" else "-"
    if ep != "-":
        ep = ep[0] + ("6" if ep[1] == "3" else "3")
    turn = "b" if pos.turn == c.WHITE else "w"
    return c.from_fen(f"{board} {turn} {castle} {ep} {pos.halfmove} 1")


def test_chess_input_is_the_same_for_both_colors():
    rng = random.Random(0)
    g = c.Game()
    for _ in range(120):
        if g.result() is not None:
            break
        pos = g.pos
        np.testing.assert_array_equal(net.encode_chess([pos]), net.encode_chess([mirrored(pos)]))
        g.push(rng.choice(g.legal()))


def test_chess_input_planes():
    pos = c.play(c.start(), c.parse_san(c.start(), "e4"))
    x = net.encode_chess([pos])[0]
    assert x.shape == (8, 8, net.CHESS_PLANES)
    assert x[3, 4, 0] == 1                          # моя пешка e4 (сходили белые)
    assert x[..., :6].sum() == 16 and x[..., 6:12].sum() == 16
    assert x[0, 0, 12:16].tolist() == [1, 1, 1, 1]  # все рокировки на месте
    assert x[..., 16].sum() == 0 and x[0, 0, 17] == 0


@pytest.mark.parametrize("fen", ["4k3/8/8/8/8/8/8/R3K3 w Q - 0 1"])
def test_material_eval_is_from_the_mover_side(fen):
    pos = c.from_fen(fen)
    after = c.play(pos, c.parse_san(pos, "Ra7"))
    assert ca.chess_material([after])[0] > 0.3      # сходили белые, у них ладья
