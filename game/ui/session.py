"""Партия в окне без Qt: режим, кто за кого играет, ходы, отмена, итог, взятые фигуры.

Режимы: 'net' - человек против сети, 'two' - вдвоём за одним ПК, 'demo' - сеть против сети.
"""
from game.ai import games
from game.core import checkers as ck

MODES = ("net", "two", "demo")
COLORS = ("white", "black", "random")
START_COUNTS = {
    "checkers": {1: 12, 2: 0},
    "chess": {1: 8, 2: 2, 3: 2, 4: 2, 5: 1, 6: 1},
}


class Session:
    def __init__(self, kind, mode="net", human=1, level="strong", game=None):
        if kind not in games.GAMES or mode not in MODES:
            raise ValueError((kind, mode))
        self.kind = kind
        self.mode = mode
        self.human = human                  # 1 белые, -1 чёрные (в режиме 'net')
        self.level = level
        self.game = game if game is not None else games.new_game(kind)
        self.recorded = False               # итог уже записан в статистику

    @property
    def pos(self):
        return self.game.pos

    def legal(self):
        return self.game.legal()

    def human_turn(self):
        if self.result() is not None:
            return False
        if self.mode == "two":
            return True
        if self.mode == "demo":
            return False
        return self.pos.turn == self.human

    def net_turn(self):
        return self.result() is None and not self.human_turn()

    def push(self, move):
        if move not in self.legal():
            raise ValueError("ход не по правилам")
        self.game.push(move)

    def undo(self):
        """Отменить ход. Против сети - до своего хода (обычно два полухода: ответ сети и свой).
        Возвращает, сколько полуходов снято."""
        if not self.game.moves:
            return 0
        n = 0
        self.game.pop()
        n += 1
        if self.mode == "net":
            while self.game.moves and self.pos.turn != self.human:
                self.game.pop()
                n += 1
        self.recorded = False
        return n

    def result(self):
        return self.game.result()

    def outcome_for_human(self):
        """'win' / 'loss' / 'draw' или None (партия идёт; не против сети - тоже None)."""
        res = self.result()
        if res is None or self.mode != "net":
            return None
        if res[0] == 0:
            return "draw"
        return "win" if res[0] == self.human else "loss"

    def last_move(self):
        return self.game.moves[-1] if self.game.moves else None

    def notation(self):
        """Записи ходов по порядку: SAN у шахмат, 'c3-d4' / 'c3:e5' у шашек."""
        if self.kind == "chess":
            return list(self.game.sans)
        return [ck.move_text(m) for m in self.game.moves]

    def captured(self):
        """{цвет: {фигура: сколько взято у этого цвета}} - по разнице с начальной расстановкой.
        Превращённая пешка считается взятой пешкой, фигура из превращения - лишней не считается."""
        counts = {1: {}, -1: {}}
        if self.kind == "checkers":
            for side in (1, -1):
                have = sum(1 for p in self.pos.board if p * side > 0)
                counts[side] = {1: 12 - have} if 12 - have else {}
            return counts
        start = START_COUNTS["chess"]
        for side in (1, -1):
            have = {}
            for _, p in self.pos.pieces():
                if p * side > 0:
                    have[abs(p)] = have.get(abs(p), 0) + 1
            for kind, n in start.items():
                lost = n - have.get(kind, 0)
                if lost > 0:
                    counts[side][kind] = lost
        return counts

    def history_keys(self):
        return [p.key for p in self.game.positions[:-1]]
