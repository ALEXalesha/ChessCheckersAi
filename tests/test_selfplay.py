"""Обучение самоигрой: цели TD-Leaf, снимок и продолжение, короткое обучение помогает."""
import random

import numpy as np
import pytest

from game.ai import net
from game.ai.adapters import checkers_material
from game.core import checkers as ck
from game.train import selfplay


class Leaf:
    def __init__(self, turn):
        self.turn = turn


def test_targets_end_with_the_outcome_and_flip_for_the_opponent():
    # белые ходят (лист после их хода: очередь чёрных), потом чёрные, белые выигрывают
    recs = [(Leaf(ck.BLACK), 0.1, ck.WHITE, False), (Leaf(ck.WHITE), -0.2, ck.BLACK, False),
            (Leaf(ck.BLACK), 0.5, ck.WHITE, False)]
    t = selfplay.leaf_targets(recs, outcome=1, lam=1.0, gamma=1.0)
    # λ = 1: чистый исход партии; у чёрных - минус
    np.testing.assert_allclose(t, [1.0, -1.0, 1.0])


def test_lambda_zero_takes_the_next_search_value():
    recs = [(Leaf(ck.BLACK), 0.1, ck.WHITE, False), (Leaf(ck.WHITE), -0.3, ck.BLACK, False)]
    t = selfplay.leaf_targets(recs, outcome=0, lam=0.0, gamma=0.9)
    np.testing.assert_allclose(t, [0.9 * 0.3, 0.0])


def test_random_reply_cuts_the_trace():
    recs = [(Leaf(ck.BLACK), 0.1, ck.WHITE, False), (Leaf(ck.WHITE), -0.3, ck.BLACK, True),
            (Leaf(ck.BLACK), 0.2, ck.WHITE, False)]
    t = selfplay.leaf_targets(recs, outcome=-1, lam=1.0, gamma=1.0)
    assert t[0] == pytest.approx(0.3)            # не исход партии (-1), а оценка лучшего ответа


def test_leaf_seen_by_the_other_side_gets_the_opposite_sign():
    # лист после хода соперника (чётное число полуходов от корня): цель с другим знаком
    recs = [(Leaf(ck.WHITE), 0.4, ck.WHITE, False)]
    assert selfplay.leaf_targets(recs, outcome=1, lam=1.0, gamma=1.0)[0] == pytest.approx(-1.0)


def test_limit_without_outcome_uses_its_own_estimate():
    recs = [(Leaf(ck.BLACK), 0.4, ck.WHITE, False)]
    assert selfplay.leaf_targets(recs, outcome=None, lam=0.7, gamma=1.0)[0] == pytest.approx(0.4)


def test_selfplay_game_gives_samples_inside_minus_one_one():
    model = net.ValueNet(4, channels=8, conv_layers=1, head=8, rng=np.random.default_rng(0))
    x, y, outcome, plies = selfplay.play_selfplay_game("checkers", model, np.random.default_rng(1), 1, 0.1,
                                                       2, 200, 0.7, 0.99)
    assert len(x) == len(y) == plies - 2 and x.dtype == np.int8
    assert np.all(np.abs(y) <= 1.0)


TINY = {"net": {"channels": 8, "conv_layers": 2, "head": 16}, "depth": 1, "games_per_task": 3,
        "eval_every": 10 ** 9, "snapshots": {"novice": 12, "medium": 24}, "buffer": 20000}


def test_snapshot_and_resume(tmp_path):
    t = selfplay.Trainer("checkers", tmp_path / "run", None, threads=2, seed=3, **TINY)
    t.log.echo = False
    t.run(total=24)
    w = t.model.arrays()
    t2 = selfplay.Trainer("checkers", tmp_path / "run", None, threads=2, seed=3, **TINY)
    t2.log.echo = False
    assert t2.resume()
    assert t2.played == t.played >= 24 and t2.filled == t.filled and t2.opt.t == t.opt.t
    for k in w:
        np.testing.assert_array_equal(t2.model.arrays()[k], w[k])
    assert set(t2.taken) == {"novice", "medium"}
    assert t2.threads_used == [2]                  # для паспорта: сколько процессов играло
    assert "продолжаю со снимка" in (tmp_path / "run" / "train.log").read_text(encoding="utf-8")


def quiet_positions(n, seed=0):
    rng = random.Random(seed)
    out, pos = [], ck.start()
    while len(out) < n:
        moves = ck.legal_moves(pos)
        if not moves or rng.random() < 0.01:
            pos = ck.start()
            continue
        pos = ck.play(pos, rng.choice(moves))
        if not ck.captures(pos):
            out.append(pos)
    return out


def test_short_training_learns_that_material_matters(tmp_path):
    """Сети не говорили, что шашки ценны. После 300 партий самоигры её оценка спокойных
    позиций уже заметно совпадает с перевесом материала, а у необученной - нет.
    (Против случайного игрока на глубине 1 короткая проверка шумит: даже необученная сеть
    с обязательными взятиями в поиске иногда выигрывает почти всё.)"""
    cfg = {**TINY, "net": {"channels": 16, "conv_layers": 2, "head": 32}, "snapshots": {}, "buffer": 50000}
    t = selfplay.Trainer("checkers", tmp_path / "run", None, threads=3, seed=5, **cfg)
    t.log.echo = False
    ps = quiet_positions(2000)
    mat = checkers_material(ps)

    def corr():
        return float(np.corrcoef(t.model.value(net.encode_checkers(ps)), mat)[0, 1])
    before = corr()
    t.run(total=300)
    after = corr()
    assert abs(before) < 0.3 and after > 0.5


def test_passport_resumes_and_refines_close_pairs(tmp_path, monkeypatch):
    """Подсчёт паспорта прерывается и продолжается с места; пары соседних уровней в пределах
    погрешности дополняются партиями (решение Алексея 10.10), партии - те же, что при подсчёте сразу."""
    from functools import partial

    from aikit import tournament
    from game.ai import games, models
    monkeypatch.setitem(games.CHECKS, "checkers", [("vs_random", {"kind": "random"})])
    monkeypatch.setitem(games.LEVEL_DEPTH, "checkers", {"novice": 1, "medium": 1, "strong": 1})
    t = selfplay.Trainer("checkers", tmp_path / "run", tmp_path / "out", threads=2, seed=3, **TINY)
    t.log.echo = False
    t.run(total=24)
    pp = t.finish(eval_games=4, minutes=0)            # время вышло сразу: модели есть, проверок нет
    assert models.has_model("checkers", tmp_path / "out")
    assert all(not lv["checks"] for lv in pp["levels"])
    pp = selfplay.run_passport("checkers", tmp_path / "out", threads=2, base=4, step=4, cap=8, chunk=3,
                               log=lambda *_: None)
    for lv in pp["levels"]:
        c = lv["checks"]["vs_random"]
        assert c["games"] in (4, 8) and c["games"] == len(c["results"])
        model = models.load_level(models.model_path("checkers", tmp_path / "out"), lv["key"])
        play = partial(games.play_one, game="checkers", subject={"kind": "net", "level": lv["key"], "depth": 1},
                       opponent={"kind": "random"}, model=model)
        assert tournament.run(play, c["games"], selfplay.CHECK_SEED["checkers"]) == c["results"]
    keys = [lv["key"] for lv in pp["levels"]]
    res = {lv["key"]: lv["checks"]["vs_random"]["results"] for lv in pp["levels"]}
    for a, b in zip(keys, keys[1:]):
        if len(res[a]) == 4 and len(res[b]) == 4:
            assert tournament.different(res[a], res[b]) or tournament.saturated(res[a], res[b])
