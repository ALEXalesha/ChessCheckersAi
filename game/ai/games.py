"""Описание двух игр в одном месте: правила, адаптер поиска, оценка по материалу, вход сети,
бот «жадный», уровни сети и проверки для паспорта (spec §6).

Игрок задаётся словарём (spec) - так его можно передать в другой процесс турнира:
    {"kind": "random"} | {"kind": "greedy"} | {"kind": "material", "depth": 4}
    {"kind": "net", "level": "strong", "depth": 4, "path": None}  (path None - models/<игра>.npz)
"""
from game.ai import adapters, bots, models, net
from game.core import checkers as ck

GAMES = ("checkers", "chess")

# Глубина поиска сети на каждом уровне (вместе со снимком обучения) - для окна и паспорта.
LEVEL_DEPTH = {
    "checkers": {"novice": 2, "medium": 4, "strong": 6},
    "chess": {"novice": 1, "medium": 2, "strong": 3},
}
# В окне сильный уровень ещё и ограничен по времени (spec §2: до 2-3 с на ход).
LEVEL_TIME = {"novice": 1.0, "medium": 2.0, "strong": 3.0}

# Проверки паспорта: соперники и правила партий.
CHECKS = {
    "checkers": [("vs_random", {"kind": "random"}), ("vs_greedy", {"kind": "greedy"}),
                 ("vs_material4", {"kind": "material", "depth": 4}),
                 ("vs_material6", {"kind": "material", "depth": 6})],
    "chess": [("vs_random", {"kind": "random"}), ("vs_greedy", {"kind": "greedy"}),
              ("vs_material2", {"kind": "material", "depth": 2}),
              ("vs_material3", {"kind": "material", "depth": 3})],
}
# Первые полуходы партии проверки - случайные (у шахмат - из короткой книги), чтобы партии
# с одинаковым началом не повторялись: число берётся из диапазона по зерну партии.
OPENING = {"checkers": (2, 4), "chess": (2, 4)}
MAX_PLIES = {"checkers": 300, "chess": 300}


def adapter(game):
    if game == "checkers":
        return adapters.CHECKERS
    from game.ai import chess_adapter
    return chess_adapter.CHESS


def material(game):
    if game == "checkers":
        return adapters.checkers_material
    from game.ai import chess_adapter
    return chess_adapter.chess_material


def encoder(game):
    return net.encode_checkers if game == "checkers" else net.encode_chess


def planes(game):
    return net.CHECKERS_PLANES if game == "checkers" else net.CHESS_PLANES


def new_game(game):
    if game == "checkers":
        return ck.Game()
    from game.core import chess
    return chess.Game()


def greedy_gain(game):
    if game == "checkers":
        return lambda pos, m: len(m[1])
    from game.ai import chess_adapter
    return chess_adapter.material_gain


def book(game):
    if game == "checkers":
        return None
    from game.ai import chess_adapter
    return chess_adapter.book_moves


def net_eval(game, level="strong", path=None, model=None):
    model = model if model is not None else models.cached_level(path or models.model_path(game), level)
    return net.NetEval(model, encoder(game))


def make_player(game, spec, rng, model=None):
    kind = spec["kind"]
    if kind == "random":
        return bots.RandomBot(rng)
    if kind == "greedy":
        return bots.GreedyBot(rng, greedy_gain(game))
    if kind == "material":
        return bots.SearchBot(adapter(game), material(game), spec["depth"], rng=rng)
    if kind == "net":
        level = spec.get("level", "strong")
        depth = spec.get("depth", LEVEL_DEPTH[game][level])
        return bots.SearchBot(adapter(game), net_eval(game, level, spec.get("path"), model), depth)
    raise ValueError(f"неизвестный игрок {spec!r}")


def play_one(i, rng, subject_first, game, subject, opponent, model=None):
    """Одна партия турнира: 'W' / 'D' / 'L' для проверяемого игрока (subject)."""
    lo, hi = OPENING[game]
    opening = int(rng.integers(lo, hi + 1))
    me = make_player(game, subject, rng, model)
    other = make_player(game, opponent, rng)
    white, black = (me, other) if subject_first else (other, me)
    res, _, _ = bots.play(new_game(game), white, black, rng, opening, book(game), MAX_PLIES[game])
    if res == 0:
        return "D"
    return "W" if (res == 1) == subject_first else "L"
