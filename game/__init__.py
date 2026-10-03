"""ChessCheckersAi: русские шашки и шахматы против нейросети, которая научилась играть сама.

Вход игры по контракту PythonAiGames: GAME_INFO и create_widget(ctx). Qt загружается
только в create_widget - правила, поиск и обучение работают без него.
"""
from game.version import VERSION

GAME_INFO = {
    "id": "chesscheckers",
    "title": {"ru": "Шашки и шахматы с нейросетью", "en": "Checkers & Chess AI"},
    "summary": {"ru": "Русские шашки и шахматы против сети, которая училась сама с собой",
                "en": "Russian checkers and chess against a self-taught neural network"},
    "preview": "docs/preview.png",
    "version": VERSION,
}

APP_NAME = "ChessCheckersAi"


def create_widget(ctx):
    """ctx: aikit.Context. Виджет со своим меню, доской и панелями."""
    from game.ui.widget import GameWidget
    return GameWidget(ctx)
