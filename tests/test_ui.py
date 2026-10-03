"""Окно offscreen: ходы мышью, ответ сети, отмена, превращение, PGN, режимы, темы и язык,
окно не подвисает во время поиска, закрытие останавливает потоки за 2 секунды.

Никаких видимых окон и захвата мыши: QT_QPA_PLATFORM=offscreen (tests/conftest.py), мышь -
события QTest прямо в виджет. Каждое ожидание - с тайм-аутом.
"""
import time

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QWidget

from game import APP_NAME, GAME_INFO, create_widget
from game.ai import games
from game.core import checkers as ck
from game.core import chess as ch
from game.ui.session import Session


def wait_until(app, cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return cond()


@pytest.fixture
def win(qapp, tmp_path):
    from aikit.host import make_window
    w, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=str(tmp_path / "app"))
    w.resize(1180, 780)
    w.show()
    qapp.processEvents()
    yield w
    w.close()
    qapp.processEvents()


def center(board, rc):
    return board.cell_rect(*rc).center().toPoint()


def click(board, rc):
    QTest.mouseClick(board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center(board, rc))


def test_game_info_follows_the_contract():
    assert set(GAME_INFO) >= {"id", "title", "summary", "preview", "version"}
    assert set(GAME_INFO["title"]) == {"ru", "en"} and GAME_INFO["id"].isascii()


def test_two_players_click_click_and_drag(qapp, win):
    g = win.game
    g.change("game", "checkers")
    g.change("mode", "two")
    g.start_game()
    board = g.play.board
    click(board, ck.rc(ck.parse_square("c3")))
    assert board.selected == ck.rc(ck.parse_square("c3"))
    click(board, ck.rc(ck.parse_square("d4")))
    assert g.session.notation() == ["c3-d4"]
    # чёрные перетаскивают f6 на g5 (после того как доехала шашка белых)
    assert wait_until(qapp, lambda: not board.animating(), 3)
    a, b = center(board, ck.rc(ck.parse_square("f6"))), center(board, ck.rc(ck.parse_square("g5")))
    QTest.mousePress(board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    QTest.mouseMove(board, QPoint((a.x() + b.x()) // 2, (a.y() + b.y()) // 2))
    QTest.mouseMove(board, b)
    QTest.mouseRelease(board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    assert g.session.notation() == ["c3-d4", "f6-g5"]
    assert g.play.moves.count() == 1 and "c3-d4" in g.play.moves.item(0).text()


def test_illegal_click_does_nothing(qapp, win):
    g = win.game
    g.change("mode", "two")
    g.start_game()
    click(g.play.board, ck.rc(ck.parse_square("c3")))
    click(g.play.board, ck.rc(ck.parse_square("c5")))
    assert g.session.notation() == []


def test_mandatory_captures_are_highlighted(qapp, win):
    g = win.game
    g.start_session(Session("checkers", "two", game=ck.Game(ck.from_squares(white=["c3", "a1"], black=["d4"]))))
    assert g.play.board.mandatory() == {ck.rc(ck.parse_square("c3"))}


def test_network_replies_and_undo_takes_back_both_moves(qapp, win):
    g = win.game
    g.change("game", "checkers")
    g.change("mode", "net")
    g.change("color", "white")
    g.change("level", "novice")
    g.start_game()
    g.on_move_chosen(ck.parse_move(g.session.pos, "c3-d4"))
    assert wait_until(qapp, lambda: len(g.session.game.moves) == 2, 15)
    assert g.session.human_turn()
    g.undo()
    assert g.session.game.moves == [] and g.session.human_turn()


def test_network_moves_first_when_human_is_black(qapp, win):
    g = win.game
    g.change("mode", "net")
    g.change("color", "black")
    g.change("level", "novice")
    g.start_game()
    assert g.flipped and g.play.board.flipped
    assert wait_until(qapp, lambda: len(g.session.game.moves) == 1, 15)


def test_window_answers_while_the_network_thinks(qapp, win, monkeypatch):
    """Поиск в отдельном потоке: таймер окна тикает без провалов, пока сеть думает 2 секунды."""
    monkeypatch.setitem(games.LEVEL_TIME, "strong", 2.0)
    monkeypatch.setitem(games.LEVEL_DEPTH["checkers"], "strong", 40)
    g = win.game
    g.change("game", "checkers")
    g.change("mode", "net")
    g.change("color", "black")
    g.change("level", "strong")
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
    timer.start(20)
    g.start_game()
    assert wait_until(qapp, lambda: len(g.session.game.moves) == 1, 20)
    timer.stop()
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    # сеть думала заметное время, а таймер окна всё это время тикал почти ровно
    assert ticks[-1] - ticks[0] > 0.5 and len(ticks) > 15
    assert max(gaps) < 0.3 and sorted(gaps)[len(gaps) // 2] < 0.06


def test_closing_stops_the_search_within_two_seconds(qapp, tmp_path, monkeypatch):
    from aikit.host import make_window
    monkeypatch.setitem(games.LEVEL_TIME, "strong", 30.0)
    monkeypatch.setitem(games.LEVEL_DEPTH["checkers"], "strong", 60)
    w, _ = make_window(GAME_INFO, create_widget, APP_NAME, root=str(tmp_path / "app2"))
    w.show()
    g = w.game
    g.change("mode", "net")
    g.change("color", "black")
    g.change("level", "strong")
    g.start_game()
    assert wait_until(qapp, lambda: g.ai.busy(), 5)
    started = time.time()
    w.close()
    assert time.time() - started < 2.0
    assert not g.ai.busy()


def test_chess_promotion_choice(qapp, win):
    g = win.game
    g.start_session(Session("chess", "two", game=ch.Game(ch.from_fen("7k/P7/8/8/8/8/8/K7 w - - 0 1"))))
    board = g.play.board
    click(board, ch.rc(ch.parse_square("a7")))
    click(board, ch.rc(ch.parse_square("a8")))
    assert board.promo is not None and g.session.notation() == []
    rect = next(r for r, kind, _ in board.promo_rects() if kind == ch.KNIGHT)
    QTest.mouseClick(board, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, rect.center().toPoint())
    assert g.session.notation() == ["a8=N"]


def test_pgn_save_and_open(qapp, win, tmp_path):
    g = win.game
    game = ch.Game()
    for s in ("e4", "e5", "Nf3"):
        game.push_san(s)
    g.change("mode", "two")
    g.start_session(Session("chess", "two", game=game))
    path = tmp_path / "game.pgn"
    assert g.save_pgn(path)
    g.start_game()
    back = g.load_pgn(path)
    assert back.sans == ["e4", "e5", "Nf3"] and g.session.notation() == ["e4", "e5", "Nf3"]
    assert g.play.pgn_row.isVisible()


def test_win_is_recorded_once(qapp, win):
    g = win.game
    g.change("mode", "net")
    pos = ck.from_squares(white=["c3"], black=["d4"])
    g.start_session(Session("checkers", "net", 1, "medium", game=ck.Game(pos)))
    g.on_move_chosen(ck.legal_moves(pos)[0])
    g.after_change()
    g.refresh()
    e = g.ctx.stats.entry("checkers/medium")
    assert (e["games"], e["wins"]) == (1, 1)
    assert g.play.status.objectName() == "statusWin"


def test_thoughts_show_a_score_for_every_move(qapp, win):
    g = win.game
    g.change("mode", "two")
    g.change("show_thoughts", True)
    g.start_game()
    assert wait_until(qapp, lambda: g.play.board.thoughts is not None, 15)
    assert set(g.play.board.thoughts) == set(g.session.legal())
    assert g.play.board.best in g.session.legal()


def test_demo_plays_by_itself_and_pauses(qapp, win):
    g = win.game
    g.change("mode", "demo")
    g.change("level", "novice")
    g.change("demo_delay_ms", 0)
    g.start_game()
    assert wait_until(qapp, lambda: len(g.session.game.moves) >= 4, 30)
    g.toggle_pause()
    n = len(g.session.game.moves)
    wait_until(qapp, lambda: False, 0.6)
    assert len(g.session.game.moves) == n
    assert g.play.demo_box.isVisible()


def test_board_cells_map_back_both_ways(qapp, win):
    board = win.game.play.board
    for flipped in (False, True):
        board.set_flipped(flipped)
        for r in range(8):
            for c in range(8):
                assert board.cell_at(board.cell_rect(r, c).center()) == (r, c)


def test_theme_and_language_change_on_the_fly(qapp, win):
    g = win.game
    g.ctx.set_lang("en")
    assert g.menu.play_button.text() == "Play"
    g.ctx.set_lang("ru")
    assert g.menu.play_button.text() == "Играть"
    g.ctx.set_theme("light")
    assert g.play.board.colors["bg"] == "#e8ecf3"


def test_every_string_exists_in_both_languages():
    from game.ui.i18n import translator
    assert translator().missing() == {}


def wrapped_labels(root):
    return [w for w in root.findChildren(QLabel) if w.wordWrap()]


@pytest.mark.parametrize("page", ["menu", "play", "stats", "settings"])
def test_wrapped_labels_are_never_capped_in_height(qapp, win, page):
    """Ловушка TicTacToeAi 1.0.0: фиксированная высота обрезала перенесённый текст."""
    g = win.game
    g.change("mode", "net")
    if page == "play":
        g.start_game()
    else:
        g.show_page(page)
    qapp.processEvents()
    for w in wrapped_labels(g.pages[page]):
        assert w.maximumHeight() == 16777215, w.text()


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_texts_fit_at_minimum_size_with_bigger_fonts(qapp, win, lang):
    """Окно минимального размера, шрифт на 10% больше (на настоящем экране текст шире, чем
    в offscreen): каждой видимой подписи с переносом хватает высоты."""
    g = win.game
    g.ctx.set_lang(lang)
    g.change("mode", "net")
    g.change("game", "chess")
    win.setStyleSheet(win.styleSheet() + "\n* { font-size: 15.4px; }")
    win.resize(win.minimumSize())
    for page in ("menu", "play", "settings"):
        if page == "play":
            g.start_game()
        else:
            g.show_page(page)
        qapp.processEvents()
        for w in wrapped_labels(g.pages[page]):
            if w.isVisible() and w.text():
                assert w.heightForWidth(w.width()) <= w.height() + 1, (page, w.text())
    g.shutdown()


def test_widget_lives_without_a_main_window(qapp, tmp_path):
    """Контракт: игра не создаёт главное окно, её виджет вставляет оболочка."""
    from aikit.host import Context
    ctx = Context(tmp_path / "data")
    w = create_widget(ctx)
    assert isinstance(w, QWidget) and w.window() is w
    assert w.shutdown()


def test_switching_games_drops_old_thoughts(qapp, win):
    """Нашлось кадрами README: «Мысли» партии в шашки рисовались на шахматной доске и
    роняли отрисовку."""
    g = win.game
    g.change("show_thoughts", True)
    g.start_session(Session("checkers", "two"))
    assert wait_until(qapp, lambda: g.play.board.thoughts is not None, 15)
    g.start_session(Session("chess", "two"))
    assert g.play.board.thoughts is None
    win.grab()
    assert wait_until(qapp, lambda: g.play.board.thoughts is not None, 15)
    assert set(g.play.board.thoughts) == set(g.session.legal())
