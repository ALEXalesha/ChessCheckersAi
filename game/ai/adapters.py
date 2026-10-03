"""Адаптеры игр для поиска (game/ai/search.py) и оценка по материалу для ботов."""
import numpy as np

from game.ai.search import MATE
from game.core import checkers as ck


class CheckersAdapter:
    name = "checkers"

    moves = staticmethod(ck.legal_moves)
    play = staticmethod(ck.play)

    @staticmethod
    def key(pos):
        return pos.key

    @staticmethod
    def rule_draw(pos):
        return pos.quiet >= ck.QUIET_LIMIT

    @staticmethod
    def no_moves_score(pos):
        return -MATE                         # в шашках без ходов - поражение

    @staticmethod
    def qmoves(pos, qply=0):
        """Взятие обязательно: есть взятия - стоять нельзя, их надо доиграть."""
        caps = ck.captures(pos)
        return (caps, False) if caps else ([], True)

    @staticmethod
    def noisy(pos, m):
        return bool(m[1]) or ck.promotes(pos, m)

    @staticmethod
    def order_key(pos, m):
        return len(m[1]) + (2 if ck.promotes(pos, m) else 0)


CHECKERS = CheckersAdapter()

# Цена в шашках: простая 1, дамка 3 (дамка русских шашек ходит и бьёт издалека).
CHECKERS_VALUES = {1: 1.0, 2: 3.0}


def checkers_material(positions):
    """Перевес материала для того, кто только что сходил, сжатый в (-1, 1)."""
    out = np.empty(len(positions))
    for i, pos in enumerate(positions):
        mover = -pos.turn
        diff = 0.0
        for p in pos.board:
            if p:
                diff += CHECKERS_VALUES[abs(p)] * (1 if p * mover > 0 else -1)
        out[i] = np.tanh(diff / 8.0)
    return out
