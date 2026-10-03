"""Боты для проверок силы сети (spec §6) и партия двух игроков.

Игрок - объект с методом choose(game) -> ход, где game - партия (core.checkers.Game или
core.chess.Game) с историей. Случайность - только из переданного генератора numpy, поэтому
партия с тем же зерном повторяется ход в ход.
"""
from game.ai.search import Searcher


def _pick(rng, items):
    return items[int(rng.integers(len(items)))]


class RandomBot:
    name = "random"

    def __init__(self, rng):
        self.rng = rng

    def choose(self, game):
        return _pick(self.rng, game.legal())


class GreedyBot:
    """Шашки: бьёт максимум шашек, иначе случайный ход. Шахматы: ход с наибольшим
    немедленным выигрышем материала (взятие, превращение), иначе случайный."""
    name = "greedy"

    def __init__(self, rng, gain):
        self.rng = rng
        self.gain = gain             # gain(pos, move) -> число

    def choose(self, game):
        moves = game.legal()
        gains = [self.gain(game.pos, m) for m in moves]
        best = max(gains)
        return _pick(self.rng, [m for m, g in zip(moves, gains) if g == best])


class SearchBot:
    """Альфа-бета на заданную глубину с данной оценкой (материал или сеть). Глубина
    фиксирована, без лимита времени - иначе партии не повторялись бы. rng - порядок равных
    ходов в корне (у бота по материалу много равных ходов)."""
    name = "search"

    def __init__(self, adapter, evaluate, depth, rng=None, quiescence=True):
        self.searcher = Searcher(adapter, evaluate, rng=rng, quiescence=quiescence)
        self.depth = depth

    def choose(self, game):
        history = [p.key for p in game.positions[:-1]]
        return self.searcher.search(game.pos, depth=self.depth, history=history).move


def play(game, white, black, rng=None, opening=0, book=None, max_plies=400):
    """Сыграть партию до конца. opening - сколько первых полуходов случайные (из book(pos),
    если дана, иначе из всех ходов). Возвращает (исход для белых 1/0/-1, причина, полуходов).
    max_plies - предел длины партии в проверках: дальше ничья (причина 'limit')."""
    plies = 0
    while True:
        res = game.result()
        if res is not None:
            return res[0], res[1], plies
        if plies >= max_plies:
            return 0, "limit", plies
        if plies < opening:
            options = book(game.pos) if book is not None else None
            move = _pick(rng, options or game.legal())
        else:
            player = white if game.pos.turn == 1 else black
            move = player.choose(game)
        game.push(move)
        plies += 1
