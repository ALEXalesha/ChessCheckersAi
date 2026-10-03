"""Виджет игры (create_widget по контракту): меню, партия, статистика, настройки.

Окно ему даёт оболочка (aikit.run_standalone или ИИ-Игротека). Тема и язык приходят из
ctx и меняются на лету по ctx.changed. Файлы - только в ctx.data_dir.
"""
import gc
import random

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QListWidget, QScrollArea, QSlider, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from aikit import settings as st
from aikit import theme
from aikit.widgets import Combo, button, card, label, restyle, segmented
from game.ai import games, models
from game.core import checkers as ck
from game.core import chess as ch
from game.ui import pieces
from game.ui.ai_thread import AiController
from game.ui.board import BoardWidget
from game.ui.i18n import translator
from game.ui.session import Session
from game.version import VERSION

SCHEMA = {
    "game": ("checkers", st.choice(*games.GAMES)),
    "mode": ("net", st.choice("net", "two", "demo")),
    "color": ("white", st.choice("white", "black", "random")),
    "level": ("medium", st.choice(*models.LEVELS)),
    "show_thoughts": (False, st.boolean()),
    "demo_delay_ms": (700, st.int_range(0, 3000)),
}
NET_DELAY_MS = 150


def page_widget():
    w = QWidget()
    w.setObjectName("page")
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    return w


def fmt_time(t, seconds):
    if seconds < 90:
        return t("seconds", n=round(seconds))
    if seconds < 5400:
        return t("minutes", n=round(seconds / 60))
    return t("hours", n=f"{seconds / 3600:.1f}".replace(".", ","))


def number(n):
    return f"{n:,}".replace(",", " ")


# --- меню ---


class MenuPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.addStretch(2)
        col = QVBoxLayout()
        col.setSpacing(10)
        col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.logo = Logo(gw)
        col.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignHCenter)
        self.title = label("", "title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.title)
        self.sub = label("", "muted", wrap=True)
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.sub)
        col.addSpacing(12)

        box = card()
        box.setMaximumWidth(620)
        grid = QGridLayout(box)
        grid.setContentsMargins(22, 18, 22, 18)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        s = gw.settings
        self.captions = {}

        def row(r, key, widget):
            cap = label("", "muted")
            self.captions[key] = cap
            grid.addWidget(cap, r, 0)
            grid.addWidget(widget, r, 1)

        w, self.game_buttons = segmented({"checkers": "", "chess": ""}, lambda v: gw.change("game", v))
        row(0, "game", w)
        w, self.mode_buttons = segmented({"net": "", "two": "", "demo": ""}, lambda v: gw.change("mode", v))
        row(1, "mode", w)
        self.color_combo = Combo()
        for key in ("white", "black", "random"):
            self.color_combo.addItem("", key)
        self.color_combo.currentIndexChanged.connect(lambda i: gw.change("color", self.color_combo.itemData(i)))
        row(2, "color", self.color_combo)
        w, self.level_buttons = segmented({lv: "" for lv in models.LEVELS}, lambda v: gw.change("level", v))
        row(3, "level", w)
        col.addWidget(box, 0, Qt.AlignmentFlag.AlignHCenter)
        self.note = label("", "hint", wrap=True)
        self.note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # ширина задана: подпись с переносом, поставленная в раскладку с выравниванием, иначе
        # получает высоту по ширине одной строки и обрезается (кадр 03.10)
        self.note.setFixedWidth(620)
        col.addWidget(self.note, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(8)
        self.play_button = button("", "menuPrimary", gw.start_game)
        self.stats_button = button("", "menu", lambda: gw.show_page("stats"))
        self.settings_button = button("", "menu", lambda: gw.show_page("settings"))
        for b in (self.play_button, self.stats_button, self.settings_button):
            col.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(col)
        outer.addStretch(3)
        self.foot = label("", "hint")
        self.foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.foot)
        self.sync(s)

    def sync(self, s):
        self.game_buttons[s["game"]].setChecked(True)
        self.mode_buttons[s["mode"]].setChecked(True)
        self.level_buttons[s["level"]].setChecked(True)
        self.color_combo.blockSignals(True)
        self.color_combo.setCurrentIndex(("white", "black", "random").index(s["color"]))
        self.color_combo.blockSignals(False)
        self.color_combo.setEnabled(s["mode"] == "net")
        t = self.gw.t
        self.note.setText("" if self.gw.ai.has_net(s["game"]) else t("no_net", game=t(s["game"])))
        self.note.setVisible(bool(self.note.text()))
        self.logo.update()

    def retranslate(self):
        t = self.gw.t
        self.title.setText(t("app_title"))
        self.sub.setText(t("app_sub"))
        for key, cap in self.captions.items():
            cap.setText(t(key))
        for k, b in self.game_buttons.items():
            b.setText(t(k))
        for k, b in self.mode_buttons.items():
            b.setText(t("mode_" + k))
        for k, b in self.level_buttons.items():
            b.setText(t(k))
        for i, key in enumerate(("white", "black", "random")):
            self.color_combo.setItemText(i, t(key))
        self.play_button.setText(t("play"))
        self.stats_button.setText(t("stats"))
        self.settings_button.setText(t("settings"))
        self.foot.setText(t("footer", v=VERSION))
        self.sync(self.gw.settings)


class Logo(QWidget):
    """Кусок доски с шашкой и конём над заголовком меню."""

    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.setFixedSize(QSize(176, 88))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = self.gw.colors()
        size = 44
        for r in range(2):
            for c in range(4):
                p.fillRect(QRectF(c * size, r * size, size, size), QColor(col["sq_dark" if (r + c) % 2 else "sq_light"]))
        pieces.draw_checker(p, QRectF(size + 3, 3, size - 6, size - 6), -2, col)
        pieces.draw_chess_piece(p, QRectF(2 * size + 2, size + 2, size - 4, size - 4), 2, col)
        pieces.draw_checker(p, QRectF(3, size + 3, size - 6, size - 6), 1, col)
        pieces.draw_chess_piece(p, QRectF(3 * size + 2, 2, size - 4, size - 4), -5, col)
        p.end()


# --- взятые фигуры ---


class CapturedView(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.kind = "checkers"
        self.counts = {1: {}, -1: {}}
        self.setMinimumHeight(56)

    def set_counts(self, kind, counts):
        self.kind, self.counts = kind, counts
        self.update()

    def sizeHint(self):
        return QSize(240, 56)

    def paintEvent(self, event):
        p = QPainter(self)
        col = self.gw.colors()
        size = 22
        for row, side in enumerate((-1, 1)):          # сверху взятые чёрные, снизу белые
            x = 0
            for kind in sorted(self.counts.get(side, {}), reverse=True):
                for _ in range(self.counts[side][kind]):
                    rect = QRectF(x, row * (size + 4), size, size)
                    pieces.draw_piece(p, rect, self.kind, side * kind, col)
                    x += size * (0.55 if self.kind == "checkers" else 0.7)
                    if x > self.width() - size:
                        break
        p.end()


# --- партия ---


class PlayPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(18)
        self.board = BoardWidget()
        self.board.moveChosen.connect(gw.on_move_chosen)
        root.addWidget(self.board, 1)

        side = card()
        side.setFixedWidth(330)
        col = QVBoxLayout(side)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(6)
        self.heading = label("", "section", wrap=True)
        col.addWidget(self.heading)
        self.status = label("", "status", wrap=True)
        col.addWidget(self.status)
        self.substatus = label("", "muted", wrap=True)
        self.substatus.setMinimumHeight(38)     # только снизу: перенос строк не обрезается
        self.substatus.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        col.addWidget(self.substatus)
        self.moves_caption = label("", "muted")
        col.addWidget(self.moves_caption)
        self.moves = QListWidget()
        self.moves.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.moves.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.moves.setMinimumHeight(60)
        col.addWidget(self.moves, 1)
        self.captured_caption = label("", "muted")
        col.addWidget(self.captured_caption)
        self.captured = CapturedView(gw)
        col.addWidget(self.captured)
        self.thoughts_box = QCheckBox("")
        self.thoughts_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.thoughts_box.toggled.connect(lambda on: gw.change("show_thoughts", on))
        col.addWidget(self.thoughts_box)
        self.thoughts_hint = label("", "hint", wrap=True)
        col.addWidget(self.thoughts_hint)

        self.demo_box = QWidget()
        dl = QHBoxLayout(self.demo_box)
        dl.setContentsMargins(0, 0, 0, 0)
        self.pause_button = button("", None, gw.toggle_pause)
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(0, 3000)
        self.speed.setInvertedAppearance(True)       # вправо - быстрее (пауза меньше)
        self.speed.setValue(gw.settings["demo_delay_ms"])
        self.speed.valueChanged.connect(lambda v: gw.change("demo_delay_ms", int(v)))
        dl.addWidget(self.pause_button)
        dl.addWidget(self.speed, 1)
        col.addWidget(self.demo_box)

        row = QHBoxLayout()
        self.undo_button = button("", None, gw.undo)
        self.flip_button = button("", None, gw.flip)
        row.addWidget(self.undo_button)
        row.addWidget(self.flip_button)
        col.addLayout(row)
        self.pgn_row = QWidget()
        pr = QHBoxLayout(self.pgn_row)
        pr.setContentsMargins(0, 0, 0, 0)
        self.save_button = button("", None, gw.save_pgn_dialog)
        self.open_button = button("", None, gw.open_pgn_dialog)
        pr.addWidget(self.save_button)
        pr.addWidget(self.open_button)
        col.addWidget(self.pgn_row)
        last = QHBoxLayout()
        self.again_button = button("", "primary", gw.start_game)
        self.menu_button = button("", None, lambda: gw.show_page("menu"))
        last.addWidget(self.again_button, 1)
        last.addWidget(self.menu_button, 1)
        col.addLayout(last)
        self.keys_hint = label("", "hint", wrap=True)
        self.keys_hint.setMinimumHeight(16)
        col.addWidget(self.keys_hint)
        root.addWidget(side)
        self.side = side

    def fit_labels(self):
        """Подписи с переносом получают высоту по своей ширине: раскладка Qt сама её не
        учитывает и при нехватке места сжала бы их, обрезав строки."""
        for w in self.side.findChildren(QLabel):
            if w.wordWrap() and w.width() > 0:
                need = w.heightForWidth(w.width())
                base = 38 if w is self.substatus else 0
                w.setMinimumHeight(max(base, need))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_labels()

    def retranslate(self):
        t = self.gw.t
        self.moves_caption.setText(t("moves"))
        self.captured_caption.setText(t("captured"))
        self.thoughts_box.setText(t("thoughts"))
        self.thoughts_hint.setText(t("thoughts_hint"))
        self.undo_button.setText(t("undo"))
        self.flip_button.setText(t("flip"))
        self.save_button.setText(t("save_pgn"))
        self.open_button.setText(t("open_pgn"))
        self.again_button.setText(t("again"))
        self.menu_button.setText(t("menu"))
        self.keys_hint.setText(t("keys"))
        self.fit_labels()
        self.pause_button.setText(t("resume") if self.gw.paused else t("pause"))


# --- статистика ---


def table(headers):
    tw = QTableWidget(0, len(headers))
    tw.setHorizontalHeaderLabels(headers)
    tw.verticalHeader().setVisible(False)
    tw.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tw.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    tw.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    tw.setShowGrid(False)
    tw.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tw.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header = tw.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    header.setHighlightSections(False)
    return tw


def fit_height(tw):
    tw.resizeRowsToContents()
    tw.setFixedHeight(tw.horizontalHeader().height() + sum(tw.rowHeight(r) for r in range(tw.rowCount())) + 4)


def item(text, align=Qt.AlignmentFlag.AlignCenter):
    it = QTableWidgetItem(text)
    it.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    return it


class StatsPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = page_widget()
        scroll.setWidget(body)
        self.col = QVBoxLayout(body)
        self.col.setContentsMargins(26, 22, 26, 22)
        self.col.setSpacing(14)
        top = QHBoxLayout()
        self.heading = label("", "heading")
        top.addWidget(self.heading)
        top.addStretch(1)
        self.menu_button = button("", None, lambda: gw.show_page("menu"))
        top.addWidget(self.menu_button)
        self.col.addLayout(top)
        mine = card()
        mc = QVBoxLayout(mine)
        mc.setContentsMargins(18, 14, 18, 14)
        self.mine_title = label("", "section")
        mc.addWidget(self.mine_title)
        self.table = table([""] * 6)
        mc.addWidget(self.table)
        self.col.addWidget(mine)
        self.net_cards = {}
        for kind in games.GAMES:
            c = card()
            lay = QVBoxLayout(c)
            lay.setContentsMargins(18, 14, 18, 14)
            title = label("", "section")
            text = label("", "muted", wrap=True)
            checks = table([""] * 6)
            foot = label("", "hint", wrap=True)
            for w in (title, text, checks, foot):
                lay.addWidget(w)
            self.net_cards[kind] = (title, text, checks, foot)
            self.col.addWidget(c)
        self.col.addStretch(1)

    def refresh(self):
        t = self.gw.t
        self.heading.setText(t("stats_title"))
        self.menu_button.setText(t("menu"))
        self.mine_title.setText(t("your_games"))
        self.table.setHorizontalHeaderLabels([t(k) for k in ("col_game_level", "col_games", "col_wins", "col_draws",
                                                               "col_losses", "col_streak")])
        rows = [(k, lv) for k in games.GAMES for lv in models.LEVELS]
        self.table.setRowCount(len(rows))
        stats = self.gw.ctx.stats
        for r, (k, lv) in enumerate(rows):
            e = stats.entry(f"{k}/{lv}")
            self.table.setItem(r, 0, item(f"{t(k)} · {t(lv)}", Qt.AlignmentFlag.AlignLeft))
            for c, f in enumerate(("games", "wins", "draws", "losses", "best_streak"), start=1):
                self.table.setItem(r, c, item(str(e[f])))
        fit_height(self.table)
        for kind, (title, text, checks, foot) in self.net_cards.items():
            title.setText(f"{t('net_title')}: {t(kind + '_full').lower() if self.gw.ctx.lang == 'ru' else t(kind)}")
            try:
                pp = models.load_passport(kind)
            except (OSError, ValueError):
                text.setText(t("not_trained"))
                checks.hide()
                foot.hide()
                continue
            n = pp["network"]
            text.setText(t("passport_text", planes=n["planes"], channels=n["channels"], layers=n["conv_layers"],
                           head=n["head"], params=number(n["parameters"]), games=number(pp["games"]),
                           time=fmt_time(t, pp["train_seconds"])))
            names = [name for name, _ in games.CHECKS[kind]]
            checks.setColumnCount(2 + len(names))
            checks.setHorizontalHeaderLabels([t("col_level"), t("col_depth")] + [t(x) for x in names])
            checks.setRowCount(len(pp["levels"]))
            for r, lv in enumerate(pp["levels"]):
                checks.setItem(r, 0, item(t(lv["key"]), Qt.AlignmentFlag.AlignLeft))
                checks.setItem(r, 1, item(str(lv["depth"])))
                for c, name in enumerate(names, start=2):
                    ch_ = lv["checks"].get(name)
                    checks.setItem(r, c, item(f"{ch_['wins']} / {ch_['draws']} / {ch_['losses']}" if ch_ else "-"))
            fit_height(checks)
            checks.show()
            games_n = pp.get("checks_rules", {}).get("games") or 0
            foot.setText(t("checks_text", n=games_n))
            foot.show()


# --- настройки ---


class SettingsPage(QWidget):
    def __init__(self, gw):
        super().__init__()
        self.gw = gw
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 26, 22)
        outer.setSpacing(14)
        top = QHBoxLayout()
        self.heading = label("", "heading")
        top.addWidget(self.heading)
        top.addStretch(1)
        self.menu_button = button("", None, lambda: gw.show_page("menu"))
        top.addWidget(self.menu_button)
        outer.addLayout(top)
        box = card()
        box.setMaximumWidth(720)
        self.grid = QGridLayout(box)
        self.grid.setContentsMargins(22, 18, 22, 18)
        self.grid.setHorizontalSpacing(22)
        self.grid.setVerticalSpacing(16)
        self.grid.setColumnStretch(1, 1)
        self.rows = {}
        self.theme_combo = Combo()
        for k in theme.THEMES:
            self.theme_combo.addItem("", k)
        self.theme_combo.currentIndexChanged.connect(lambda i: gw.ctx.set_theme(self.theme_combo.itemData(i)))
        self._row(0, "theme", self.theme_combo)
        self.lang_combo = Combo()
        self.lang_combo.addItem("Русский", "ru")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.currentIndexChanged.connect(lambda i: gw.ctx.set_lang(self.lang_combo.itemData(i)))
        self._row(1, "language", self.lang_combo)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(gw.ctx.sound.volume)
        self.volume.valueChanged.connect(gw.ctx.set_volume)
        self._row(2, "volume", self.volume)
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(0, 3000)
        self.speed.setInvertedAppearance(True)
        self.speed.setValue(gw.settings["demo_delay_ms"])
        self.speed.valueChanged.connect(lambda v: gw.change("demo_delay_ms", int(v)))
        self._row(3, "speed", self.speed)
        outer.addWidget(box)
        self.note = label("", "hint")
        outer.addWidget(self.note)
        outer.addStretch(1)

    def _row(self, r, key, widget):
        names = QVBoxLayout()
        names.setSpacing(2)
        title = label("", "section")
        hint = label("", "hint", wrap=True)
        names.addWidget(title)
        names.addWidget(hint)
        self.grid.addLayout(names, r, 0)
        self.grid.addWidget(widget, r, 1)
        self.rows[key] = (title, hint)

    def retranslate(self):
        t = self.gw.t
        self.heading.setText(t("settings_title"))
        self.menu_button.setText(t("menu"))
        hints = {"theme": "theme_hint", "language": "language_hint", "volume": "volume_hint", "speed": "speed_hint"}
        for key, (title, hint) in self.rows.items():
            title.setText(t(key))
            hint.setText(t(hints[key]))
        for i, k in enumerate(theme.THEMES):
            self.theme_combo.setItemText(i, t(k))
        self.note.setText(t("saved_note"))
        self.sync()

    def sync(self):
        for combo, value in ((self.theme_combo, self.gw.ctx.theme), (self.lang_combo, self.gw.ctx.lang)):
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(value))
            combo.blockSignals(False)
        self.speed.blockSignals(True)
        self.speed.setValue(self.gw.settings["demo_delay_ms"])
        self.speed.blockSignals(False)


# --- сам виджет игры ---


class GameWidget(QWidget):
    def __init__(self, ctx):
        super().__init__()
        # Всё, что уже создано (Qt, numpy, модели), - в постоянное поколение сборщика мусора:
        # иначе полный проход сборщика посреди поиска держит GIL и окно замирает (в прогоне
        # всех тестов ловили паузу 0,67 с).
        gc.freeze()
        self.ctx = ctx
        self.t = translator(ctx.lang)
        self.settings = st.Settings(SCHEMA, ctx.file("settings.json"))
        self.session = None
        self.token = 0
        self.paused = False
        self.flipped = False
        self.thoughts = None
        self.best = None
        self.ai = AiController(self)
        self.ai.ready.connect(self.on_ai)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._net_go)
        self.stack = QStackedWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)
        self.menu = MenuPage(self)
        self.play = PlayPage(self)
        self.stats = StatsPage(self)
        self.settings_page = SettingsPage(self)
        self.pages = {"menu": self.menu, "play": self.play, "stats": self.stats, "settings": self.settings_page}
        for p in self.pages.values():
            self.stack.addWidget(p)
        for keys, slot in (("Ctrl+Z", self.undo), ("F", self.flip), ("Escape", lambda: self.show_page("menu")),
                           ("R", self.start_game)):
            sc = QShortcut(QKeySequence(keys), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
        ctx.changed.connect(self.on_ctx_changed)
        self.apply_theme()
        self.retranslate()
        self.show_page("menu")

    # --- общее ---

    def colors(self):
        return theme.palette(self.ctx.theme)

    def current_page(self):
        w = self.stack.currentWidget()
        return next(k for k, p in self.pages.items() if p is w)

    def show_page(self, name):
        if name != "play":
            self._invalidate()
        self.stack.setCurrentWidget(self.pages[name])
        if name == "stats":
            self.stats.refresh()
        elif name == "settings":
            self.settings_page.sync()
        elif name == "menu":
            self.menu.sync(self.settings)

    def change(self, key, value):
        if self.settings[key] == value:
            return
        self.settings.set(key, value)
        if key in ("game", "mode", "level", "color"):
            self.menu.sync(self.settings)
        elif key == "show_thoughts":
            self.thoughts = None
            self.best = None
            self.after_change()

    def on_ctx_changed(self, what):
        if what == "theme":
            self.apply_theme()
        elif what == "lang":
            self.t = translator(self.ctx.lang)
            self.retranslate()

    def apply_theme(self):
        c = self.colors()
        self.play.board.set_theme(self.ctx.theme)
        for combo in self.findChildren(Combo):
            combo.set_arrow_color(c["text"])
        self.update()

    def retranslate(self):
        self.menu.retranslate()
        self.play.retranslate()
        self.settings_page.retranslate()
        if self.current_page() == "stats":
            self.stats.refresh()
        if self.session is not None:
            self.refresh()

    def shutdown(self):
        """Окно закрывается: таймеры стоп, поиски остановить и дождаться (не дольше 2 с)."""
        self._invalidate()
        return self.ai.shutdown(2000)

    def _invalidate(self):
        self.token += 1
        self.timer.stop()
        self.ai.cancel()

    # --- партия ---

    def start_game(self):
        s = self.settings
        human = {"white": 1, "black": -1}.get(s["color"]) or random.choice((1, -1))
        self.session = Session(s["game"], s["mode"], human, s["level"])
        self.paused = False
        self.flipped = s["mode"] == "net" and human == -1
        self.play.board.set_flipped(self.flipped)
        self.stack.setCurrentWidget(self.play)
        self._invalidate()
        self.thoughts = None
        self.best = None
        self.after_change()

    def start_session(self, session):
        """Для тестов и открытия PGN: готовая партия."""
        self.session = session
        self.paused = False
        self.thoughts = None          # оценки ходов старой партии к новой не относятся
        self.best = None
        self.stack.setCurrentWidget(self.play)
        self._invalidate()
        self.after_change()

    def on_move_chosen(self, move):
        s = self.session
        if s is None or not s.human_turn() or move not in s.legal():
            return
        self._play_move(move)

    def _play_move(self, move):
        s = self.session
        before = s.pos
        capture = (bool(move[1]) if s.kind == "checkers" else ch.is_capture(before, move))
        s.push(move)
        self.play.board.set_state(s.kind, s.pos, [], s.last_move(), False)
        self.play.board.animate(move, before)
        self.ctx.sound.play("capture" if capture else "move")
        self.thoughts = None
        self.best = None
        self.after_change()

    def after_change(self):
        """После любого изменения партии: перерисовать, записать итог, запустить сеть."""
        self.token += 1
        self.timer.stop()
        self.ai.cancel()
        s = self.session
        if s is None:
            return
        self.refresh()
        res = s.result()
        if res is not None:
            outcome = s.outcome_for_human()
            if outcome and not s.recorded:
                self.ctx.stats.record(f"{s.kind}/{s.level}", outcome)
                s.recorded = True
                self.ctx.sound.play(outcome)
            elif not outcome:
                self.ctx.sound.play("draw" if res[0] == 0 else "win")
            return
        if s.net_turn():
            if s.mode == "demo" and self.paused:
                return
            delay = self.settings["demo_delay_ms"] if s.mode == "demo" else NET_DELAY_MS
            self.timer.start(max(delay, BoardWidget.ANIM_MS if self.play.board.animating() else 0))
        elif self.settings["show_thoughts"]:
            self.ai.request_thoughts(self.token, s)

    def _net_go(self):
        s = self.session
        if s is None or not s.net_turn():
            return
        self.refresh()
        if self.settings["show_thoughts"]:
            self.ai.request_thoughts(self.token, s)
        self.ai.request_move(self.token, s)

    def on_ai(self, token, kind, payload):
        if token != self.token or self.session is None:
            return
        if isinstance(payload, Exception):
            self.play.substatus.setText(self.t("error", e=payload))
            return
        if kind == "thoughts":
            self.thoughts = payload
            self.best = max(payload, key=payload.get) if payload else None
            self.play.board.set_thoughts(self.thoughts, self.best)
            return
        if payload.move is not None and self.session.net_turn():
            self._play_move(payload.move)

    def undo(self):
        s = self.session
        if s is None or self.current_page() != "play" or not s.game.moves:
            return
        self._invalidate()
        s.undo()
        self.thoughts = None
        self.best = None
        self.after_change()

    def flip(self):
        if self.current_page() != "play":
            return
        self.flipped = not self.flipped
        self.play.board.set_flipped(self.flipped)

    def toggle_pause(self):
        self.paused = not self.paused
        self.play.pause_button.setText(self.t("resume") if self.paused else self.t("pause"))
        if not self.paused:
            self.after_change()
        else:
            self._invalidate()

    # --- PGN ---

    def save_pgn(self, path):
        s = self.session
        if s is None or s.kind != "chess":
            return False
        names = {"net": ("?", "?"), "two": ("?", "?"), "demo": ("ChessCheckersAi", "ChessCheckersAi")}[s.mode]
        if s.mode == "net":
            names = ("Human", "ChessCheckersAi") if s.human == 1 else ("ChessCheckersAi", "Human")
        text = ch.to_pgn(s.game, {"White": names[0], "Black": names[1]})
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return True

    def load_pgn(self, path):
        with open(path, encoding="utf-8") as f:
            game = ch.from_pgn(f.read())
        mode = self.settings["mode"]
        human = game.pos.turn if mode == "net" else 1
        self.start_session(Session("chess", mode, human, self.settings["level"], game=game))
        return game

    def save_pgn_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, self.t("save_pgn"), "", self.t("pgn_filter"))
        if path:
            self.save_pgn(path)

    def open_pgn_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, self.t("open_pgn"), "", self.t("pgn_filter"))
        if not path:
            return
        try:
            self.load_pgn(path)
        except (OSError, ValueError, KeyError) as e:
            self.play.substatus.setText(self.t("pgn_bad", e=e))

    # --- вид ---

    def refresh(self):
        s = self.session
        if s is None:
            return
        t = self.t
        pp = self.play
        human_turn = s.human_turn()
        pp.board.set_state(s.kind, s.pos, s.legal() if human_turn else [], s.last_move(), human_turn,
                           self.thoughts if self.settings["show_thoughts"] else None,
                           self.best if self.settings["show_thoughts"] else None)
        pp.heading.setText(f"{t(s.kind + '_full')} · {t('mode_' + s.mode)}")
        res = s.result()
        if res is None:
            restyle(pp.status, "status")
            if s.mode == "net":
                pp.status.setText(t("your_move") if human_turn else t("net_thinks"))
                color = t("you_play_white") if s.human == 1 else t("you_play_black")
                text = t("you_play", color=color, level=t(s.level).lower())
            else:
                pp.status.setText(t("white_move") if s.pos.turn == 1 else t("black_move"))
                text = t("two_players") if s.mode == "two" else t("demo_text", level=t(s.level).lower())
            if s.kind == "checkers" and human_turn and ck.captures(s.pos):
                text += " " + t("must_capture")
            if not self.ai.has_net(s.kind) and s.mode != "two":
                text += " " + t("no_net", game=t(s.kind))
            pp.substatus.setText(text)
        else:
            outcome = s.outcome_for_human()
            if outcome:
                restyle(pp.status, {"win": "statusWin", "loss": "statusLoss", "draw": "statusDraw"}[outcome])
                pp.status.setText(t(outcome))
            else:
                restyle(pp.status, "statusDraw" if res[0] == 0 else "status")
                pp.status.setText(t("draw") if res[0] == 0 else t("white_wins" if res[0] == 1 else "black_wins"))
            pp.substatus.setText(t("reason_" + res[1]))
        notes = s.notation()
        start_black = s.game.positions[0].turn == -1
        lines = []
        items = ([None] + notes) if start_black else notes
        base = getattr(s.game.positions[0], "fullmove", 1)
        for i in range(0, len(items), 2):
            w = items[i] or "…"
            b = items[i + 1] if i + 1 < len(items) else ""
            lines.append(f"{base + i // 2}. {w}   {b}")
        pp.moves.clear()
        pp.moves.addItems(lines)
        pp.moves.scrollToBottom()
        pp.captured.set_counts(s.kind, s.captured())
        pp.thoughts_box.blockSignals(True)
        pp.thoughts_box.setChecked(self.settings["show_thoughts"])
        pp.thoughts_box.blockSignals(False)
        pp.demo_box.setVisible(s.mode == "demo")
        pp.pgn_row.setVisible(s.kind == "chess")
        pp.undo_button.setEnabled(bool(s.game.moves) and s.mode != "demo")
        pp.speed.blockSignals(True)
        pp.speed.setValue(self.settings["demo_delay_ms"])
        pp.speed.blockSignals(False)
        pp.fit_labels()
