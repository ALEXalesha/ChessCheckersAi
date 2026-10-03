"""Шахматы для поиска: адаптер, тихий поиск (взятия и превращения, под шахом - все ходы),
порядок взятий MVV-LVA, оценка по материалу для ботов и короткая книга начал для проверок."""
import numpy as np

from game.ai.search import MATE
from game.core import chess as c

VALUES = {c.PAWN: 1.0, c.KNIGHT: 3.0, c.BISHOP: 3.0, c.ROOK: 5.0, c.QUEEN: 9.0, c.KING: 0.0}


class ChessAdapter:
    name = "chess"

    moves = staticmethod(c.legal_moves)
    play = staticmethod(c.play)

    @staticmethod
    def key(pos):
        return pos.key

    @staticmethod
    def rule_draw(pos):
        return pos.halfmove >= 100 or c.insufficient_material(pos)

    @staticmethod
    def no_moves_score(pos):
        return -MATE if c.in_check(pos) else 0.0       # мат или пат

    @staticmethod
    def qmoves(pos):
        """Тихий поиск: под шахом стоять нельзя - все ответы; иначе взятия и превращения."""
        if c.in_check(pos):
            return c.legal_moves(pos), False
        return c.legal_captures(pos), True

    @staticmethod
    def noisy(pos, m):
        return m[2] != 0 or c.is_capture(pos, m)

    @staticmethod
    def order_key(pos, m):
        """MVV-LVA: сначала самая ценная жертва, из равных - самым дешёвым нападающим."""
        victim = c.PAWN if m[3] == c.EP else abs(pos.board[m[1]])
        attacker = abs(pos.board[m[0]])
        return (VALUES.get(victim, 0) * 10 - VALUES.get(attacker, 0)) / 100 + (VALUES[m[2]] / 10 if m[2] else 0)


CHESS = ChessAdapter()


def material_diff(pos, side):
    d = 0.0
    for _, p in pos.pieces():
        d += VALUES[abs(p)] * (1 if (p > 0) == (side == c.WHITE) else -1)
    return d


def chess_material(positions):
    """Перевес материала для того, кто только что сходил, сжатый в (-1, 1)."""
    return np.array([np.tanh(material_diff(p, -p.turn) / 10.0) for p in positions])


def material_gain(pos, m):
    """Немедленный выигрыш материала ходом: цена взятой фигуры плюс прибавка от превращения."""
    gain = 0.0
    if m[3] == c.EP:
        gain += 1.0
    elif pos.board[m[1]]:
        gain += VALUES[abs(pos.board[m[1]])]
    if m[2]:
        gain += VALUES[m[2]] - 1.0
    return gain


# Короткая книга: популярные начала на 4 полухода. Первые 2-4 полухода партии проверки
# берутся отсюда случайно, дальше играют сами игроки.
BOOK_LINES = [
    "e4 e5 Nf3 Nc6", "e4 e5 Nf3 Nf6", "e4 e5 Bc4 Nf6", "e4 e5 Nc3 Nf6", "e4 c5 Nf3 d6", "e4 c5 Nf3 Nc6",
    "e4 c5 Nc3 Nc6", "e4 e6 d4 d5", "e4 c6 d4 d5", "e4 d5 exd5 Qxd5", "e4 d6 d4 Nf6", "e4 g6 d4 Bg7",
    "e4 Nf6 e5 Nd5", "d4 d5 c4 e6", "d4 d5 c4 c6", "d4 d5 Nf3 Nf6", "d4 Nf6 c4 e6", "d4 Nf6 c4 g6",
    "d4 Nf6 Nf3 e6", "d4 f5 g3 Nf6", "c4 e5 Nc3 Nf6", "c4 c5 Nf3 Nc6", "c4 Nf6 Nc3 e6", "Nf3 d5 g3 Nf6",
    "Nf3 Nf6 c4 g6", "g3 d5 Bg2 Nf6", "b3 e5 Bb2 Nc6", "e4 e5 d4 exd4",
]
_BOOK = None


def _build_book():
    book = {}
    for line in BOOK_LINES:
        pos = c.start()
        for s in line.split():
            m = c.parse_san(pos, s)
            book.setdefault(pos.key, [])
            if m not in book[pos.key]:
                book[pos.key].append(m)
            pos = c.play(pos, m)
    return book


def book_moves(pos):
    """Ходы книги в этой позиции (список) или None, если позиции в книге нет."""
    global _BOOK
    if _BOOK is None:
        _BOOK = _build_book()
    return _BOOK.get(pos.key)
