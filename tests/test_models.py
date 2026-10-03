"""Готовые модели и паспорта: числа в паспорте пересчитываются партия в партию.

Паспорт хранит исход каждой партии каждой проверки ('W' / 'D' / 'L') и правила проверок
(зерно, случайное начало, предел длины). Тест заново играет несколько партий с теми же
зёрнами и сверяет. Быстрый прогон берёт по одной-две партии с проверки, полный (slow) -
больше. Нет модели - тесты пропускаются (модель ещё учится).
"""
from functools import partial

import pytest

from aikit import tournament
from game.ai import games, models
from game.train import selfplay


def passports():
    out = []
    for kind in games.GAMES:
        if models.has_model(kind):
            out.append((kind, models.load_passport(kind)))
    return out


CASES = [(kind, lv["key"], name) for kind, pp in passports() for lv in pp["levels"] for name in lv["checks"]]


def recheck(kind, level, name, indices):
    pp = models.load_passport(kind)
    lv = next(x for x in pp["levels"] if x["key"] == level)
    opponent = dict(games.CHECKS[kind])[name]
    model = models.load_level(models.model_path(kind), level)
    play = partial(games.play_one, game=kind, subject={"kind": "net", "level": level, "depth": lv["depth"]},
                   opponent=opponent, model=model)
    got = tournament.run(play, len(lv["checks"][name]["results"]), pp["checks_rules"]["seed"], indices=indices)
    want = "".join(lv["checks"][name]["results"][i] for i in indices)
    return got, want


def sample(name, slow):
    cheap = name in ("vs_random", "vs_greedy")
    if slow:
        return [0, 1, 2, 3, 57, 101] if cheap else [0, 1, 2, 3]
    return [0, 1] if cheap else [1]


@pytest.mark.parametrize("kind, level, name", CASES)
def test_passport_games_repeat(kind, level, name):
    got, want = recheck(kind, level, name, sample(name, slow=False))
    assert got == want


@pytest.mark.slow
@pytest.mark.parametrize("kind, level, name", CASES)
def test_passport_games_repeat_bigger_sample(kind, level, name):
    got, want = recheck(kind, level, name, sample(name, slow=True))
    assert got == want


@pytest.mark.parametrize("kind, pp", passports())
def test_passport_is_complete_and_consistent(kind, pp):
    assert pp["game"] == kind and pp["games"] > 0 and pp["train_seconds"] > 0
    assert [lv["key"] for lv in pp["levels"]] == list(models.LEVELS)
    assert pp["network"]["parameters"] == models.load_level(models.model_path(kind), "strong").count()
    for lv in pp["levels"]:
        assert lv["depth"] == games.LEVEL_DEPTH[kind][lv["key"]]
        assert set(lv["checks"]) == {name for name, _ in games.CHECKS[kind]}
        for c in lv["checks"].values():
            assert c["games"] == len(c["results"]) == pp["checks_rules"]["games"]
            assert (c["wins"], c["draws"], c["losses"]) == tuple(c["results"].count(x) for x in "WDL")
    assert pp["checks_rules"]["seed"] == selfplay.CHECK_SEED[kind]
    games_at = [lv["games"] for lv in pp["levels"]]
    assert games_at == sorted(games_at)            # новичок - раньше, сильный - конец обучения


@pytest.mark.parametrize("kind, pp", passports())
def test_trained_network_beats_random_and_greedy(kind, pp):
    strong = next(lv for lv in pp["levels"] if lv["key"] == "strong")
    for name in ("vs_random", "vs_greedy"):
        assert strong["checks"][name]["score"] >= 0.75, name
