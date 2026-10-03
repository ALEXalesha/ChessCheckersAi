"""Сеть оценки позиции после хода и вход для неё.

Сеть смотрит на позицию глазами того, кто только что сходил: «мои» и «чужие» фигуры, доска
повёрнута так, что мои всегда идут снизу вверх. Поэтому одна сеть играет обоими цветами.
Выход - одно число в (-1, 1): ожидаемый исход для сходившего, от проигрыша до победы.

Шашки: 4 плоскости 8x8 - мои простые, мои дамки, чужие простые, чужие дамки. Для чёрных
доска поворачивается на 180° (тёмные поля остаются тёмными: поле s переходит в 31 - s).

Шахматы: 12 плоскостей фигур (мои P N B R Q K, чужие P N B R Q K), 4 плоскости прав на
рокировку (мои O-O, мои O-O-O, чужие O-O, чужие O-O-O - вся плоскость 0 или 1), плоскость
поля взятия на проходе и плоскость счётчика 50 ходов (полуходы / 100). Для чёрных доска
отражается по вертикали (ряд r -> 7 - r), цвета меняются местами - это и есть симметрия
шахмат со сменой цвета, рокировки при ней остаются своими.

Сеть: свёртки 3x3 (паддинг нулями), плотный слой, один выход tanh.
"""
import json

import numpy as np

from aikit.nn import io, layers

# --- шашки ---

_CK_ROW = np.array([s // 4 for s in range(32)])
_CK_COL = np.array([2 * (s % 4) + ((s // 4) % 2) for s in range(32)])
CHECKERS_PLANES = 4


def encode_checkers(positions):
    """Список позиций -> (B, 8, 8, 4) float32 глазами сходившего в каждой."""
    n = len(positions)
    boards = np.array([p.board for p in positions], dtype=np.int8).reshape(n, 32)
    mover = np.array([-p.turn for p in positions], dtype=np.int8)
    rel = boards * mover[:, None]                     # мои > 0
    black = mover < 0
    rel[black] = rel[black][:, ::-1]                  # поворот на 180°: s -> 31 - s
    out = np.zeros((n, 8, 8, CHECKERS_PLANES), np.float32)
    for plane, value in enumerate((1, 2, -1, -2)):
        b, s = np.nonzero(rel == value)
        out[b, _CK_ROW[s], _CK_COL[s], plane] = 1.0
    return out


# --- шахматы (позиция - core.chess.Position) ---

CHESS_PLANES = 18


def encode_chess(positions):
    """Список позиций -> (B, 8, 8, 18) float32 глазами сходившего."""
    from game.core import chess
    n = len(positions)
    out = np.zeros((n, 8, 8, CHESS_PLANES), np.float32)
    for i, pos in enumerate(positions):
        mover = -pos.turn
        flip = mover == chess.BLACK
        for sq, piece in pos.pieces():
            r, c = chess.rc(sq)
            if flip:
                r = 7 - r
            mine = (piece > 0) == (mover == chess.WHITE)
            out[i, r, c, (0 if mine else 6) + abs(piece) - 1] = 1.0
        cr = pos.castling
        my_k, my_q, op_k, op_q = (chess.WK, chess.WQ, chess.BK, chess.BQ) if not flip else \
            (chess.BK, chess.BQ, chess.WK, chess.WQ)
        for plane, bit in zip(range(12, 16), (my_k, my_q, op_k, op_q)):
            if cr & bit:
                out[i, :, :, plane] = 1.0
        if pos.ep is not None:
            r, c = chess.rc(pos.ep)
            out[i, 7 - r if flip else r, c, 16] = 1.0
        out[i, :, :, 17] = min(pos.halfmove, 100) / 100.0
    return out


# --- сама сеть ---


class ValueNet:
    """Свёртки 3x3 (planes -> channels x conv_layers), плотный слой head, выход tanh."""

    def __init__(self, planes, channels=32, conv_layers=3, head=64, rng=None):
        rng = rng if rng is not None else np.random.default_rng()
        self.config = {"planes": planes, "channels": channels, "conv_layers": conv_layers, "head": head}
        items = []
        cin = planes
        for _ in range(conv_layers):
            items += [layers.Conv3x3(cin, channels, rng), layers.ReLU()]
            cin = channels
        items.append(layers.Flatten())
        items += [layers.Dense(64 * channels, head, rng), layers.ReLU(), layers.Dense(head, 1, rng), layers.Tanh()]
        self.body = layers.Sequential(items)

    def forward(self, x):
        return self.body.forward(x)

    def backward(self, dy):
        return self.body.backward(dy)

    def params(self):
        return self.body.params()

    def value(self, x, chunk=2048):
        """(B,) оценки без обучения, кусками."""
        if len(x) == 0:
            return np.zeros(0, np.float32)
        if len(x) <= chunk:
            return self.body.forward(x)[:, 0]
        return np.concatenate([self.body.forward(x[i:i + chunk])[:, 0] for i in range(0, len(x), chunk)])

    def count(self):
        return int(sum(p.size for _, p, _ in self.params()))

    def arrays(self):
        return {name: p.copy() for name, p, _ in self.params()}

    def set_arrays(self, arrays):
        for name, p, _ in self.params():
            if arrays[name].shape != p.shape:
                raise ValueError(f"{name}: {arrays[name].shape} вместо {p.shape}")
            p[...] = arrays[name]

    def save(self, path, extra=None):
        arrays = io.collect({"net": self.body})
        arrays["meta"] = np.array(json.dumps(self.config))
        for k, v in (extra or {}).items():
            arrays[k] = v
        io.save(path, arrays)

    @classmethod
    def load(cls, path):
        arrays = io.load(path)
        config = json.loads(str(arrays.pop("meta")))
        model = cls(**config)
        io.restore({"net": model.body}, arrays)
        return model


class NetEval:
    """Оценка для поиска: список позиций -> массив оценок сети для сходившего."""

    def __init__(self, model, encode):
        self.model = model
        self.encode = encode

    def __call__(self, positions):
        return self.model.value(self.encode(positions)).astype(np.float64)
