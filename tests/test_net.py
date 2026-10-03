"""Вход сети и сама сеть: глазами сходившего, одна сеть на оба цвета, сохранение уровней."""
import random

import numpy as np
import pytest

from game.ai import models, net
from game.core import checkers as ck


def flipped(pos):
    """Та же позиция с другой стороны доски: цвета наоборот, доска на 180°, очередь наоборот."""
    board = [-p for p in reversed(pos.board)]
    return ck.Position(board, -pos.turn, pos.quiet)


def random_positions(n, seed=0):
    rng = random.Random(seed)
    out = []
    pos = ck.start()
    while len(out) < n:
        moves = ck.legal_moves(pos)
        if not moves:
            pos = ck.start()
            continue
        pos = ck.play(pos, rng.choice(moves))
        out.append(pos)
    return out


def test_start_after_white_move_shows_my_men_at_the_bottom():
    pos = ck.play(ck.start(), ck.parse_move(ck.start(), "c3-d4"))
    x = net.encode_checkers([pos])[0]
    assert x[..., 0].sum() == 12 and x[..., 2].sum() == 12 and x[..., 1].sum() == 0
    assert x[3, 3, 0] == 1                     # d4 - моя простая
    assert x[:3, :, 0].sum() == 11 and x[5:, :, 2].sum() == 12


def test_both_colors_see_the_same_thing_from_their_side():
    for pos in random_positions(200, seed=1):
        a = net.encode_checkers([pos])
        b = net.encode_checkers([flipped(pos)])
        np.testing.assert_array_equal(a, b)


def test_only_dark_squares_are_used():
    x = net.encode_checkers(random_positions(100, seed=2)).sum(axis=(0, 3))
    for r in range(8):
        for c in range(8):
            if (r + c) % 2:
                assert x[r, c] == 0


def test_left_right_mirror_is_not_a_symmetry_of_checkers():
    """Почему у шашек нет аугментации отражением (spec §3 её предлагал): зеркало слева
    направо переводит тёмные поля в светлые, на них шашки не стоят."""
    for s in range(32):
        r, c = ck.rc(s)
        assert ck.sq(r, 7 - c) is None


def test_net_output_is_inside_minus_one_one_and_batch_independent():
    model = net.ValueNet(net.CHECKERS_PLANES, channels=8, conv_layers=2, head=16, rng=np.random.default_rng(0))
    x = net.encode_checkers(random_positions(10, seed=3))
    v = model.value(x)
    assert v.shape == (10,) and np.all(np.abs(v) < 1)
    np.testing.assert_allclose(model.value(x[3:4]), v[3:4], rtol=1e-5)


def test_levels_round_trip(tmp_path):
    nets = {lv: net.ValueNet(4, channels=4, conv_layers=1, head=8, rng=np.random.default_rng(i))
            for i, lv in enumerate(models.LEVELS)}
    path = tmp_path / "checkers.npz"
    models.save_levels(path, nets)
    x = net.encode_checkers(random_positions(5))
    for lv, n in nets.items():
        np.testing.assert_array_equal(models.load_level(path, lv).value(x), n.value(x))
    with pytest.raises(KeyError):
        models.load_level(path, "grandmaster")
