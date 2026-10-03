"""Поиск: совпадает с полным минимаксом, находит выигрыш, слушается времени и флага."""
import random
import time

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from game.ai.adapters import CHECKERS, checkers_material
from game.ai.search import MATE, Searcher, minimax
from game.core import checkers as ck


def zero(positions):
    return np.zeros(len(positions))


def hashed(positions):
    """Оценка-«шум»: разная у разных позиций, одинаковая у одной. Так минимакс и альфа-бета
    почти никогда не равны случайно."""
    return np.array([((p.key * 2654435761) % 1999) / 1000.0 - 0.999 for p in positions])


def random_position(seed, plies):
    rng = random.Random(seed)
    pos = ck.start()
    for _ in range(plies):
        moves = ck.legal_moves(pos)
        if not moves:
            break
        pos = ck.play(pos, rng.choice(moves))
    return pos


@settings(max_examples=60, deadline=None)
@given(st.integers(0, 10 ** 6), st.integers(0, 60), st.integers(1, 4), st.sampled_from(["material", "hashed"]))
def test_alpha_beta_equals_full_minimax(seed, plies, depth, kind):
    evaluate = checkers_material if kind == "material" else hashed
    pos = random_position(seed, plies)
    if not ck.legal_moves(pos):
        return
    s = Searcher(CHECKERS, evaluate, quiescence=False)
    r = s.search(pos, depth=depth)
    expected = minimax(CHECKERS, evaluate, pos, depth)
    assert r.score == pytest.approx(expected, abs=1e-9)
    # второй поиск той же позиции на ту же глубину берёт границы из таблицы - и не врёт
    assert s.search(pos, depth=depth).score == pytest.approx(expected, abs=1e-9)
    # ход, который выбрал поиск, на самом деле даёт эту оценку
    assert -minimax(CHECKERS, evaluate, ck.play(pos, r.move), depth - 1, 1) == pytest.approx(r.score, abs=1e-9)


@pytest.mark.parametrize("text, best", [
    ("W:WKb2,d4:Bf6,c7", "d4-e5"),        # жертва: чёрные обязаны бить, дамка забирает всё
    ("W:WKb6,a7:Be5,d6", "a7-b8"),        # в дамки - и через ход у чёрных ничего
])
def test_finds_the_forced_win(text, best):
    pos = ck.from_text(text)
    winning = {ck.move_text(m) for m in ck.legal_moves(pos)
               if -minimax(CHECKERS, zero, ck.play(pos, m), 3, 1) > MATE - 1}
    r = Searcher(CHECKERS, checkers_material).search(pos, depth=6)
    assert winning == {best}
    assert ck.move_text(r.move) == best and r.score > MATE - 1


def test_nearer_win_scores_higher_than_a_farther_one():
    now = ck.from_squares(white_kings=["a1"], black=["c3"])                 # выигрыш этим ходом
    later = ck.from_text("W:WKb2,d4:Bf6,c7")                                 # выигрыш через ход
    s_now = Searcher(CHECKERS, checkers_material).search(now, depth=5).score
    s_later = Searcher(CHECKERS, checkers_material).search(later, depth=5).score
    assert s_now > s_later > MATE - 1


def slow_material(positions):
    time.sleep(0.01)
    return checkers_material(positions)


def test_time_limit_is_respected():
    started = time.time()
    r = Searcher(CHECKERS, slow_material).search(ck.start(), max_time=0.3)
    assert time.time() - started < 0.55
    assert r.move in ck.legal_moves(ck.start()) and r.depth >= 1


def test_stop_flag_stops_the_search_soon():
    started = time.time()
    r = Searcher(CHECKERS, checkers_material).search(ck.start(), depth=12,
                                                     stop=lambda: time.time() - started > 0.2)
    assert time.time() - started < 1.0
    assert r.move in ck.legal_moves(ck.start()) and 1 <= r.depth < 12


def test_transpositions_inside_a_search_give_exact_scores():
    """Партия ход за ходом, таблица чистая на каждом ходу: внутри поиска на глубину 4 есть
    перестановки ходов, и границы в таблице должны давать ровно оценку минимакса."""
    rng = random.Random(4)
    s = Searcher(CHECKERS, hashed, quiescence=False)
    pos = ck.start()
    for _ in range(40):
        moves = ck.legal_moves(pos)
        if not moves:
            break
        s.clear()
        r = s.search(pos, depth=4)
        assert r.score == pytest.approx(minimax(CHECKERS, hashed, pos, 4), abs=1e-9)
        pos = ck.play(pos, rng.choice(moves))


def test_no_moves_gives_no_move_and_a_loss():
    pos = ck.from_squares(white=["a1"], black=["b2", "c3"])
    r = Searcher(CHECKERS, checkers_material).search(pos, depth=3)
    assert r.move is None and r.score == -MATE


def test_repetition_counts_as_a_draw():
    # каждый ход белых ведёт в позицию из истории партии - значит, оценка ничейная
    pos = ck.from_squares(white_kings=["a1"], black_kings=["h8", "g7"], white=["c1"])
    s = Searcher(CHECKERS, checkers_material)
    plain = s.search(pos, depth=2).score
    hist = {ck.play(pos, m).key for m in ck.legal_moves(pos)}
    s.clear()
    assert s.search(pos, depth=2, history=hist).score == 0.0
    assert plain != 0.0


def test_analyse_gives_every_move_an_exact_score():
    pos = random_position(5, 20)
    s = Searcher(CHECKERS, hashed, quiescence=False)
    scores = s.analyse(pos, depth=2)
    assert set(scores) == set(ck.legal_moves(pos))
    for m, v in scores.items():
        assert v == pytest.approx(-minimax(CHECKERS, hashed, ck.play(pos, m), 1, 1), abs=1e-9)


def test_leaf_of_the_principal_variation_has_the_root_score():
    pos = random_position(11, 30)
    r = Searcher(CHECKERS, hashed, quiescence=False).search(pos, depth=3)
    leaf_value = float(hashed([r.leaf])[0])          # для сходившего в листе
    sign = 1 if -r.leaf.turn == pos.turn else -1
    assert sign * leaf_value == pytest.approx(r.score, abs=1e-9)
    assert len(r.pv) == 3 and r.pv[0] == r.move


@settings(max_examples=80, deadline=None)
@given(st.integers(0, 10 ** 6), st.integers(0, 50),
       st.lists(st.tuples(st.floats(-1.2, 1.2), st.floats(0.01, 1.0)), min_size=3, max_size=8))
def test_any_window_keeps_the_fail_soft_contract(seed, plies, windows):
    """Один Searcher, одна позиция, окна подряд разные - таблица копит границы. Ответ r для
    окна (a, b): r <= a - значит истинная оценка не больше r; r >= b - не меньше r; иначе
    ровно она."""
    pos = random_position(seed, plies)
    if not ck.legal_moves(pos):
        return
    v = minimax(CHECKERS, hashed, pos, 3)
    s = Searcher(CHECKERS, hashed, quiescence=False)
    for lo, width in windows:
        a, b = lo, lo + width
        r, _, _ = s._negamax(pos, 3, a, b, 0, set())
        if r <= a:
            assert v <= r + 1e-9
        elif r >= b:
            assert v >= r - 1e-9
        else:
            assert r == pytest.approx(v, abs=1e-9)
