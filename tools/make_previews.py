"""Кадры для README программой, offscreen (никогда снимком экрана).

    python tools/make_previews.py

Пишет docs/preview_*.png: меню, шашки и шахматы с «Мыслями сети», статистика - в тёмной и
светлой темах, и docs/preview.png (16:9) для списка игр Игротеки. Данные игрока - во
временной папке.
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from aikit import offscreen  # noqa: E402

offscreen.setup(force=True)

from PySide6.QtWidgets import QApplication  # noqa: E402

from aikit.host import make_window  # noqa: E402
from game import APP_NAME, GAME_INFO, create_widget  # noqa: E402
from game.core import checkers as ck  # noqa: E402
from game.core import chess as ch  # noqa: E402
from game.ui.session import Session  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
CHECKERS_LINE = ["c3-d4", "f6-g5", "b2-c3", "g7-f6", "a3-b4", "b6-a5"]
CHESS_LINE = ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "d3", "Bc5"]


def wait(app, cond, timeout=20):
    end = time.time() + timeout
    while time.time() < end and not cond():
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def main():
    os.makedirs(DOCS, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    root = tempfile.mkdtemp(prefix="chesscheckersai-shots-")
    window, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=root)
    window.resize(1280, 800)
    window.show()
    g = window.game
    g.change("mode", "two")
    g.change("level", "strong")
    shots = []
    for theme in ("dark", "light"):
        ctx.set_theme(theme)
        suffix = "" if theme == "dark" else "_light"
        g.change("game", "checkers")
        g.show_page("menu")
        wait(app, lambda: True, 0.2)
        shots.append((f"preview_menu{suffix}.png", window.grab()))

        game = ck.Game()
        for t in CHECKERS_LINE:
            game.push(ck.parse_move(game.pos, t))
        g.change("show_thoughts", True)
        g.start_session(Session("checkers", "two", game=game))
        wait(app, lambda: g.play.board.thoughts is not None and not g.play.board.animating())
        shots.append((f"preview_checkers{suffix}.png", window.grab()))

        game = ch.Game()
        for t in CHESS_LINE:
            game.push_san(t)
        g.start_session(Session("chess", "two", game=game))
        wait(app, lambda: g.play.board.thoughts is not None and not g.play.board.animating())
        shots.append((f"preview_chess{suffix}.png", window.grab()))
        g.change("show_thoughts", False)

        g.show_page("stats")
        wait(app, lambda: True, 0.2)
        shots.append((f"preview_stats{suffix}.png", window.grab()))
    for name, pix in shots:
        pix.save(os.path.join(DOCS, name))
        print(name, pix.width(), "x", pix.height())
    # 16:9 для списка игр: кадр шахмат в тёмной теме, обрезанный по высоте
    ctx.set_theme("dark")
    g.change("show_thoughts", True)
    game = ch.Game()
    for t in CHESS_LINE:
        game.push_san(t)
    g.start_session(Session("chess", "two", game=game))
    window.resize(1280, 720)
    wait(app, lambda: g.play.board.thoughts is not None and not g.play.board.animating())
    window.grab().save(os.path.join(DOCS, "preview.png"))
    print("preview.png")
    window.close()


if __name__ == "__main__":
    main()
