"""Фигуры и шашки, нарисованные своим кодом (QPainter), без чужих наборов (spec §5: у многих
наборов лицензия CC BY-SA или неясная).

Каждая фигура описана в квадрате 100x100 и масштабируется в клетку. Белые - светлая
заливка с тёмным контуром, чёрные - тёмная заливка со светлым контуром (цвета из темы).
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF


def _poly(points):
    path = QPainterPath()
    path.addPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
    path.closeSubpath()
    return path


def _base(path, top=80, bottom=90, half=30):
    path.addRoundedRect(QRectF(50 - half, top, 2 * half, bottom - top), 3, 3)


def pawn_path():
    p = QPainterPath()
    p.addEllipse(QPointF(50, 30), 12, 12)
    p.addPath(_poly([(42, 40), (58, 40), (63, 50), (57, 52), (62, 76), (38, 76), (43, 52), (37, 50)]))
    _base(p, 74, 88, 24)
    return p.simplified()


def rook_path():
    p = QPainterPath()
    p.addPath(_poly([(26, 16), (35, 16), (35, 24), (45, 24), (45, 16), (55, 16), (55, 24), (65, 24), (65, 16),
                     (74, 16), (74, 34), (66, 40), (66, 72), (34, 72), (34, 40), (26, 34)]))
    _base(p, 72, 88, 28)
    return p.simplified()


def bishop_path():
    p = QPainterPath()
    p.addEllipse(QPointF(50, 15), 6, 6)
    mitre = QPainterPath()
    mitre.moveTo(50, 20)
    mitre.cubicTo(70, 34, 68, 52, 60, 60)
    mitre.lineTo(40, 60)
    mitre.cubicTo(32, 52, 30, 34, 50, 20)
    mitre.closeSubpath()
    p.addPath(mitre)
    p.addPath(_poly([(40, 60), (60, 60), (63, 66), (58, 68), (62, 76), (38, 76), (42, 68), (37, 66)]))
    _base(p, 74, 88, 26)
    return p.simplified()


def bishop_slit():
    p = QPainterPath()
    p.moveTo(56, 32)
    p.lineTo(46, 44)
    return p


def queen_path():
    p = QPainterPath()
    for x, y in ((18, 26), (33, 18), (50, 14), (67, 18), (82, 26)):
        p.addEllipse(QPointF(x, y), 5.5, 5.5)
    p.addPath(_poly([(18, 30), (30, 56), (33, 22), (43, 52), (50, 18), (57, 52), (67, 22), (70, 56), (82, 30),
                     (72, 66), (28, 66)]))
    p.addPath(_poly([(28, 64), (72, 64), (68, 76), (32, 76)]))
    _base(p, 74, 88, 30)
    return p.simplified()


def king_path():
    p = QPainterPath()
    p.addPath(_poly([(46, 6), (54, 6), (54, 12), (60, 12), (60, 19), (54, 19), (54, 26), (46, 26), (46, 19),
                     (40, 19), (40, 12), (46, 12)]))
    body = QPainterPath()
    body.moveTo(50, 30)
    body.cubicTo(60, 26, 82, 28, 80, 44)
    body.cubicTo(78, 54, 70, 60, 68, 66)
    body.lineTo(32, 66)
    body.cubicTo(30, 60, 22, 54, 20, 44)
    body.cubicTo(18, 28, 40, 26, 50, 30)
    body.closeSubpath()
    p.addPath(body)
    p.addPath(_poly([(32, 64), (68, 64), (66, 76), (34, 76)]))
    _base(p, 74, 88, 30)
    return p.simplified()


def knight_path():
    p = _poly([(32, 80), (70, 80), (74, 70), (77, 52), (74, 36), (66, 24), (60, 20), (58, 10), (51, 18),
               (44, 18), (36, 24), (22, 42), (16, 54), (20, 60), (30, 58), (40, 52), (46, 50), (40, 62),
               (30, 74)])
    _base(p, 76, 90, 28)
    return p.simplified()


def knight_eye():
    p = QPainterPath()
    p.addEllipse(QPointF(44, 32), 3.2, 3.2)
    return p


PATHS = {}


def chess_path(kind):
    if not PATHS:
        PATHS.update({1: pawn_path(), 2: knight_path(), 3: bishop_path(), 4: rook_path(), 5: queen_path(),
                      6: king_path()})
    return PATHS[kind]


def draw_chess_piece(p: QPainter, rect: QRectF, piece: int, colors: dict):
    """piece - код core.chess (знак - цвет)."""
    white = piece > 0
    fill = QColor(colors["piece_white"] if white else colors["piece_black"])
    edge = QColor(colors["piece_white_edge"] if white else colors["piece_black_edge"])
    p.save()
    p.translate(rect.x(), rect.y())
    s = rect.width() / 100.0
    p.scale(s, s)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(edge, 3.2)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(fill)
    p.drawPath(chess_path(abs(piece)))
    p.setBrush(edge)
    if abs(piece) == 2:
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(knight_eye())
    elif abs(piece) == 3:
        p.setBrush(Qt.BrushStyle.NoBrush)
        slit = QPen(edge, 3.0)
        slit.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(slit)
        p.drawPath(bishop_slit())
    p.restore()


def draw_checker(p: QPainter, rect: QRectF, piece: int, colors: dict):
    """piece - код core.checkers: ±1 простая, ±2 дамка."""
    white = piece > 0
    fill = QColor(colors["piece_white"] if white else colors["piece_black"])
    edge = QColor(colors["piece_white_edge"] if white else colors["piece_black_edge"])
    p.save()
    p.translate(rect.x(), rect.y())
    s = rect.width() / 100.0
    p.scale(s, s)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # тень-ободок снизу: шашка выглядит толстой
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(edge.darker(115) if white else edge.darker(160))
    p.drawEllipse(QPointF(50, 54), 38, 38)
    p.setPen(QPen(edge, 3.0))
    p.setBrush(fill)
    p.drawEllipse(QPointF(50, 49), 38, 38)
    # кольцо и корона дамки - цветом, который виден на заливке: у чёрных светлым (в светлой
    # теме контур чёрных тёмный, и корона на чёрной шашке пропадала - кадр 03.10)
    detail = edge if white else QColor(colors["piece_white"]).darker(112)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(detail, 2.0))
    p.drawEllipse(QPointF(50, 49), 27, 27)
    if abs(piece) == 2:
        crown_pen = QPen(detail, 2.6)
        crown_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(crown_pen)
        p.setBrush(detail)
        crown = QPolygonF([QPointF(x, y) for x, y in
                           ((32, 58), (30, 38), (40, 48), (50, 34), (60, 48), (70, 38), (68, 58))])
        p.drawPolygon(crown)
    p.restore()


def draw_piece(p, rect, kind, piece, colors):
    if kind == "checkers":
        draw_checker(p, rect, piece, colors)
    else:
        draw_chess_piece(p, rect, piece, colors)
