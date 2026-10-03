"""Доска: клетки, фигуры, подсветки, ход мышью (нажать-нажать или перетащить), плавное
движение, переворот, «Мысли сети», выбор фигуры при превращении пешки.

Доска ничего не знает о правилах: ей дают позицию, список законных ходов и что подсветить,
она отдаёт выбранный ход сигналом moveChosen. Клетка - (ряд, столбец), ряд 0 - первая
горизонталь белых.
"""
from PySide6.QtCore import QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from aikit import theme
from game.core import checkers as ck
from game.core import chess as ch
from game.ui import pieces

FILES = "abcdefgh"


# --- что доске нужно от позиции и хода ---


def cells(kind, pos):
    """[(ряд, столбец, фигура)] для непустых клеток."""
    if kind == "checkers":
        return [(*ck.rc(s), p) for s, p in enumerate(pos.board) if p]
    return [(*ch.rc(sq), p) for sq, p in pos.pieces()]


def move_from(kind, m):
    return ck.rc(m[0][0]) if kind == "checkers" else ch.rc(m[0])


def move_to(kind, m):
    return ck.rc(m[0][-1]) if kind == "checkers" else ch.rc(m[1])


def move_path(kind, m):
    """Клетки, через которые идёт фигура (у шашек - все поля взятия)."""
    if kind == "checkers":
        return [ck.rc(s) for s in m[0]]
    return [ch.rc(m[0]), ch.rc(m[1])]


def is_capture(kind, pos, m):
    if kind == "checkers":
        return bool(m[1])
    return ch.is_capture(pos, m)


def piece_at(kind, pos, rc):
    r, c = rc
    if kind == "checkers":
        s = ck.sq(r, c)
        return 0 if s is None else pos.board[s]
    return pos.board[ch.sq_of(r, c)]


class BoardWidget(QWidget):
    moveChosen = Signal(object)

    ANIM_MS = 220

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.kind = "checkers"
        self.pos = ck.start()
        self.moves = []
        self.last = None
        self.interactive = False
        self.flipped = False
        self.colors = theme.palette("dark")
        self.thoughts = None          # {ход: оценка для того, чья очередь}
        self.best = None
        self.selected = None          # клетка выбранной фигуры
        self.waypoints = []           # шашки: промежуточные поля, если ходов в клетку несколько
        self.drag_pos = None
        self.pressed_at = None
        self.promo = None             # (клетка куда, [ходы]) - выбор фигуры превращения
        self.anim = None              # (фигура, [клетки пути], доля 0..1)
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.valueChanged.connect(self._on_anim)
        self._animation.finished.connect(self._anim_done)

    # --- состояние ---

    def set_state(self, kind, pos, moves, last=None, interactive=False, thoughts=None, best=None):
        changed = kind != self.kind or pos is not self.pos
        self.kind, self.pos, self.moves, self.last = kind, pos, list(moves), last
        self.interactive = interactive
        self.thoughts = thoughts
        self.best = best
        if changed or not interactive:
            self.selected = None
            self.waypoints = []
            self.promo = None
            self.drag_pos = None
        self.update()

    def set_thoughts(self, thoughts, best=None):
        self.thoughts = thoughts
        self.best = best
        self.update()

    def set_flipped(self, flipped):
        self.flipped = flipped
        self.update()

    def set_theme(self, name):
        self.colors = theme.palette(name)
        self.update()

    def animate(self, move, before):
        """Плавно провести фигуру хода move из позиции before (позиция уже новая)."""
        path = move_path(self.kind, move)
        piece = piece_at(self.kind, before, path[0])
        self.anim = (piece, path, 0.0)
        self._animation.stop()
        self._animation.setDuration(self.ANIM_MS * max(1, len(path) - 1))
        self._animation.start()

    def animating(self):
        return self.anim is not None

    def _on_anim(self, value):
        if self.anim is not None:
            self.anim = (self.anim[0], self.anim[1], float(value))
            self.update()

    def _anim_done(self):
        self.anim = None
        self.update()

    # --- геометрия ---

    def geometry_(self):
        side = min(self.width(), self.height())
        margin = max(14.0, side * 0.04)
        size = (side - 2 * margin) / 8.0
        x0 = (self.width() - 8 * size) / 2
        y0 = (self.height() - 8 * size) / 2
        return x0, y0, size

    def cell_rect(self, r, c):
        x0, y0, size = self.geometry_()
        col = 7 - c if self.flipped else c
        row = r if self.flipped else 7 - r
        return QRectF(x0 + col * size, y0 + row * size, size, size)

    def cell_at(self, point):
        x0, y0, size = self.geometry_()
        col = int((point.x() - x0) // size)
        row = int((point.y() - y0) // size)
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        c = 7 - col if self.flipped else col
        r = row if self.flipped else 7 - row
        return r, c

    # --- выбор хода ---

    def moves_from(self, rc):
        return [m for m in self.moves if move_from(self.kind, m) == rc]

    def targets(self):
        if self.selected is None:
            return {}
        out = {}
        for m in self.moves_from(self.selected):
            if self.waypoints:
                path = move_path(self.kind, m)[1:]
                if not _subsequence(self.waypoints, path):
                    continue
            out.setdefault(move_to(self.kind, m), []).append(m)
        return out

    def mandatory(self):
        """Шашки: клетки фигур, которые обязаны бить (подсветка, пока ничего не выбрано)."""
        if self.kind != "checkers" or not self.moves or not self.moves[0][1]:
            return set()
        return {move_from(self.kind, m) for m in self.moves}

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.interactive or self.anim is not None:
            return
        point = event.position()
        if self.promo is not None:
            self._promo_click(point)
            return
        rc = self.cell_at(point)
        if rc is None:
            return
        if self.selected is not None and rc != self.selected:
            if self._try_target(rc):
                return
        if self.moves_from(rc):
            self.selected = rc
            self.waypoints = []
            self.pressed_at = rc
            self.drag_pos = None
        else:
            self.selected = None
            self.waypoints = []
        self.update()

    def mouseMoveEvent(self, event):
        if self.pressed_at is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.drag_pos = event.position()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        was_drag = self.drag_pos is not None
        self.drag_pos = None
        start = self.pressed_at
        self.pressed_at = None
        if was_drag and start is not None:
            rc = self.cell_at(event.position())
            if rc is not None and rc != start:
                self._try_target(rc)
        self.update()

    def _try_target(self, rc):
        """Клик по клетке при выбранной фигуре. True - клик ушёл в ход (или в выбор)."""
        targets = self.targets()
        if rc in targets:
            options = targets[rc]
            if len(options) == 1:
                self._choose(options[0])
                return True
            if self.kind == "chess":
                self.promo = (rc, options)          # разные превращения
                self.update()
                return True
            # шашки: несколько путей в одну клетку - ждём промежуточное поле
            self.waypoints.append(rc)
            if len({tuple(m[0]) for m in self.targets().get(rc, [])}) == 1:
                self._choose(self.targets()[rc][0])
            self.update()
            return True
        if self.kind == "checkers" and self.selected is not None:
            through = [m for m in self.moves_from(self.selected) if rc in move_path(self.kind, m)[1:-1]
                       and _subsequence(self.waypoints, move_path(self.kind, m)[1:])]
            if through:
                self.waypoints.append(rc)
                self.update()
                return True
        return False

    def _choose(self, move):
        self.selected = None
        self.waypoints = []
        self.promo = None
        self.update()
        self.moveChosen.emit(move)

    def promo_rects(self):
        """Клетки выбора фигуры превращения: столбец под/над полем превращения."""
        rc, options = self.promo
        kinds = [ch.QUEEN, ch.ROOK, ch.BISHOP, ch.KNIGHT]
        r, c = rc
        step = -1 if r == 7 else 1
        out = []
        for i, k in enumerate(kinds):
            m = next((o for o in options if o[2] == k), None)
            if m is not None:
                out.append((self.cell_rect(r + step * i, c), k, m))
        return out

    def _promo_click(self, point):
        for rect, _, m in self.promo_rects():
            if rect.contains(point):
                self._choose(m)
                return
        self.promo = None
        self.update()

    # --- рисование ---

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = self.colors
        x0, y0, size = self.geometry_()
        light, dark = QColor(col["sq_light"]), QColor(col["sq_dark"])
        for r in range(8):
            for c in range(8):
                # a1 тёмное и в шашках, и в шахматах
                p.fillRect(self.cell_rect(r, c), dark if (r + c) % 2 == 0 else light)
        self._draw_coords(p, x0, y0, size)
        if self.last is not None:
            tint = QColor(col["last_move"])
            tint.setAlpha(110)
            for rc in (move_from(self.kind, self.last), move_to(self.kind, self.last)):
                p.fillRect(self.cell_rect(*rc), tint)
        if self.kind == "chess" and ch.in_check(self.pos):
            k = self.pos.kings[self.pos.turn]
            if k is not None:
                glow = QColor(col["bad"])
                glow.setAlpha(150)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(glow)
                p.drawEllipse(self.cell_rect(*ch.rc(k)).adjusted(size * 0.06, size * 0.06, -size * 0.06, -size * 0.06))
        if self.interactive and self.selected is None and self.promo is None:
            ring = QColor(col["capture_hint"])
            p.setPen(QPen(ring, max(2.0, size * 0.06)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for rc in self.mandatory():
                p.drawRect(self.cell_rect(*rc).adjusted(size * 0.05, size * 0.05, -size * 0.05, -size * 0.05))
        if self.thoughts:
            self._draw_thoughts(p, size)
        if self.selected is not None:
            sel = QColor(col["select"])
            p.setPen(QPen(sel, max(2.0, size * 0.07)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(self.cell_rect(*self.selected).adjusted(size * 0.04, size * 0.04, -size * 0.04, -size * 0.04))
        moving = None
        if self.anim is not None:
            moving = self.anim[1][-1]
        dragging = self.selected if self.drag_pos is not None else None
        for r, c, piece in cells(self.kind, self.pos):
            if (r, c) == moving or (r, c) == dragging:
                continue
            pieces.draw_piece(p, self._piece_rect(self.cell_rect(r, c)), self.kind, piece, col)
        self._draw_targets(p, size)
        for rc in self.waypoints:
            p.setPen(QPen(QColor(col["select"]), max(2.0, size * 0.05), Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(self.cell_rect(*rc).adjusted(size * 0.2, size * 0.2, -size * 0.2, -size * 0.2))
        if self.anim is not None:
            piece, path, t = self.anim
            here = _along(path, t)
            rect = self.cell_rect(*path[0])
            a = self.cell_rect(*here[0])
            b = self.cell_rect(*here[1])
            f = here[2]
            rect.moveTo(a.x() + (b.x() - a.x()) * f, a.y() + (b.y() - a.y()) * f)
            pieces.draw_piece(p, self._piece_rect(rect), self.kind, piece, col)
        if dragging is not None:
            piece = piece_at(self.kind, self.pos, dragging)
            rect = QRectF(self.drag_pos.x() - size / 2, self.drag_pos.y() - size / 2, size, size)
            pieces.draw_piece(p, self._piece_rect(rect), self.kind, piece, col)
        if self.promo is not None:
            self._draw_promo(p, size)
        p.end()

    @staticmethod
    def _piece_rect(rect):
        pad = rect.width() * 0.06
        return rect.adjusted(pad, pad, -pad, -pad)

    def _draw_coords(self, p, x0, y0, size):
        f = QFont(self.font())
        f.setPixelSize(max(9, int(size * 0.16)))
        p.setFont(f)
        p.setPen(QColor(self.colors["coord"]))
        for i in range(8):
            c = 7 - i if self.flipped else i
            r = i if self.flipped else 7 - i
            p.drawText(QRectF(x0 + i * size, y0 + 8 * size, size, y0 if y0 > 4 else 14),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, FILES[c])
            p.drawText(QRectF(max(0.0, x0 - 18), y0 + i * size, 16, size),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(r + 1))

    def _draw_targets(self, p, size):
        col = self.colors
        hint = QColor(col["hint"])
        hint.setAlpha(90)
        for rc, ms in self.targets().items():
            rect = self.cell_rect(*rc)
            if any(is_capture(self.kind, self.pos, m) for m in ms):
                p.setPen(QPen(hint, max(3.0, size * 0.08)))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(rect.adjusted(size * 0.08, size * 0.08, -size * 0.08, -size * 0.08))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(hint)
                p.drawEllipse(rect.center(), size * 0.15, size * 0.15)

    def _draw_thoughts(self, p, size):
        """«Мысли сети»: клетки ходов окрашены оценкой (-1 красный ... +1 зелёный), у фигур -
        цвет их лучшего хода; лучший ход - стрелка."""
        name = "light" if self.colors is theme.PALETTES["light"] else "dark"
        per_piece = {}
        shown = {}
        for m, v in self.thoughts.items():
            v = max(-1.0, min(1.0, v))
            frm = move_from(self.kind, m)
            per_piece[frm] = max(per_piece.get(frm, -2), v)
            if self.selected is None or frm == self.selected:
                to = move_to(self.kind, m)
                if self.selected is not None or to not in shown or v > shown[to]:
                    shown[to] = v
        f = QFont(self.font())
        f.setPixelSize(max(9, int(size * 0.2)))
        f.setBold(True)
        p.setFont(f)
        for rc, v in shown.items():
            rect = self.cell_rect(*rc)
            color = QColor(*theme.heat(v, name))
            color.setAlpha(190)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(rect.adjusted(size * 0.08, size * 0.08, -size * 0.08, -size * 0.08), 6, 6)
            p.setPen(QColor(self.colors["text"]))
            p.drawText(rect.adjusted(0, size * 0.55, 0, 0), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       score_text(v))
        for rc, v in per_piece.items():
            color = QColor(*theme.heat(v, name))
            p.setPen(QPen(color, max(2.0, size * 0.07)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(self.cell_rect(*rc).adjusted(size * 0.05, size * 0.05, -size * 0.05, -size * 0.05))
        if self.best is not None:
            a = self.cell_rect(*move_from(self.kind, self.best)).center()
            b = self.cell_rect(*move_to(self.kind, self.best)).center()
            _arrow(p, a, b, QColor(self.colors["accent"]), size)

    def _draw_promo(self, p, size):
        shade = QColor(0, 0, 0, 120)
        p.fillRect(self.rect(), shade)
        sign = 1 if self.pos.turn == ch.WHITE else -1
        for rect, kind, _ in self.promo_rects():
            p.setPen(QPen(QColor(self.colors["accent"]), 2))
            p.setBrush(QColor(self.colors["surface"]))
            p.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 8, 8)
            pieces.draw_piece(p, self._piece_rect(rect), "chess", sign * kind, self.colors)


def score_text(v):
    """+0.42 / −0.42 / 0.00: настоящий минус, у нуля без знака."""
    if abs(v) < 0.005:
        return "0.00"
    return f"{v:+.2f}".replace("-", "−")


def _subsequence(small, big):
    it = iter(big)
    return all(x in it for x in small)


def _along(path, t):
    """Где фигура на пути при доле t: (клетка от, клетка до, доля между ними)."""
    if len(path) < 2:
        return path[0], path[0], 0.0
    seg = min(len(path) - 2, int(t * (len(path) - 1)))
    f = t * (len(path) - 1) - seg
    return path[seg], path[seg + 1], min(1.0, max(0.0, f))


def _arrow(p, a, b, color, size):
    color = QColor(color)
    color.setAlpha(210)
    pen = QPen(color, max(3.0, size * 0.1))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = max(1.0, (dx * dx + dy * dy) ** 0.5)
    ux, uy = dx / length, dy / length
    head = size * 0.3
    tip = QPointF(b.x() - ux * size * 0.12, b.y() - uy * size * 0.12)
    p.drawLine(a, QPointF(tip.x() - ux * head * 0.8, tip.y() - uy * head * 0.8))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    left = QPointF(tip.x() - ux * head - uy * head * 0.6, tip.y() - uy * head + ux * head * 0.6)
    right = QPointF(tip.x() - ux * head + uy * head * 0.6, tip.y() - uy * head - ux * head * 0.6)
    p.drawPolygon(QPolygonF([tip, left, right]))

