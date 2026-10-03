"""Иконка программы: клетки доски с шашкой и конём, нарисованные тем же кодом, что фигуры.
Её же собирает в .ico build.py."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPixmap

from aikit import theme
from game.ui import pieces


def render(size=256):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    col = theme.palette("dark")
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), size * 0.16, size * 0.16)
    p.setClipPath(clip)
    half = size / 2
    for r in range(2):
        for c in range(2):
            p.fillRect(QRectF(c * half, r * half, half, half), QColor(col["sq_dark" if (r + c) % 2 == 0 else "sq_light"]))
    pieces.draw_checker(p, QRectF(half * 0.08, half * 1.08, half * 0.84, half * 0.84), -2, col)
    pieces.draw_chess_piece(p, QRectF(half * 1.04, half * 0.04, half * 0.92, half * 0.92), 2, col)
    p.end()
    return img


def app_icon():
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(render(s)))
    return icon
