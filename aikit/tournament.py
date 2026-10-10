"""Турнир для паспорта модели: N партий, у каждой своё зерно, итог партия за партией.

Партия i получает генератор numpy.random.default_rng([seed, i]) и цвет: чётные партии
проверяемый игрок начинает, нечётные - соперник. Поэтому любую партию можно пересчитать
отдельно и сверить с паспортом, а партии - раздать по процессам.

play_one(i, rng, subject_first) -> 'W' | 'D' | 'L' с точки зрения проверяемого игрока.
"""
import numpy as np


def game_rng(seed, i):
    return np.random.default_rng([int(seed), int(i)])


def run(play_one, games, seed, indices=None, processes=1, pool=None):
    """Строка исходов 'WDL...' длиной games (или по indices - для выборки в тестах)."""
    idx = list(range(games)) if indices is None else list(indices)       # games не нужен, если есть indices
    jobs = [(play_one, i, seed) for i in idx]
    if pool is not None:
        out = pool.map(_job, jobs)
    elif processes > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(processes) as p:
            out = p.map(_job, jobs)
    else:
        out = [_job(j) for j in jobs]
    return "".join(out)


def _job(job):
    play_one, i, seed = job
    r = play_one(i, game_rng(seed, i), i % 2 == 0)
    if r not in ("W", "D", "L"):
        raise ValueError(f"партия {i}: исход {r!r}")
    return r


def summary(results):
    """{'games', 'wins', 'draws', 'losses', 'score', 'ci95', 'results'}; score - (победы + ничьи/2) /
    партии, ci95 - полуширина 95% доверительного интервала очков (нормальное приближение по
    разбросу очков за партию 1 / 0.5 / 0)."""
    w, d, l = results.count("W"), results.count("D"), results.count("L")
    n = max(len(results), 1)
    score = (w + d / 2) / n
    return {"games": len(results), "wins": w, "draws": d, "losses": l,
            "score": round(score, 4), "ci95": round(ci95(results), 4), "results": results}


def _points(results):
    return [{"W": 1.0, "D": 0.5, "L": 0.0}[r] for r in results]


def ci95(results):
    """Полуширина 95% интервала для доли очков: 1.96 * стандартная ошибка среднего; если все
    партии кончились одинаково - 3 / n («правило трёх»)."""
    x = _points(results)
    n = len(x)
    if n < 2:
        return 1.0
    m = sum(x) / n
    var = sum((v - m) ** 2 for v in x) / (n - 1)
    if var == 0:
        return 3.0 / n          # все партии одинаковы: «правило трёх», а не ложный ноль
    return 1.96 * (var / n) ** 0.5


def different(a, b):
    """Отличаются ли два итога сильнее погрешности: разница очков больше 1.96 * sqrt(se_a^2 + se_b^2).
    a и b - строки исходов 'WDL...'."""
    def se2(r):
        return (ci95(r) / 1.96) ** 2
    sa = sum(_points(a)) / max(len(a), 1)
    sb = sum(_points(b)) / max(len(b), 1)
    return abs(sa - sb) > 1.96 * (se2(a) + se2(b)) ** 0.5


def saturated(a, b):
    """Оба итога в одном крае (все победы или все поражения): больше партий разницы не покажут."""
    return (set(a) == {"W"} and set(b) == {"W"}) or (set(a) == {"L"} and set(b) == {"L"})
