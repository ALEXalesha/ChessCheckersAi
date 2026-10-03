import os
import re

import pytest

import build
from game import GAME_INFO
from game.version import VERSION

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def nsi():
    with open(os.path.join(ROOT, "installer.nsi"), encoding="utf-8-sig") as f:
        return f.read()


def test_version_is_the_same_in_the_game_and_the_installer():
    assert build.version() == VERSION == GAME_INFO["version"]


def test_installer_registers_under_the_app_name_in_russian():
    text = nsi()
    assert re.search(r'!define APP "ChessCheckersAi"', text)
    assert '!insertmacro MUI_LANGUAGE "Russian"' in text
    assert r'OutFile "dist\${APP}-${VERSION}-setup.exe"' in text
    assert "RequestExecutionLevel user" in text
    assert r"$APPDATA\${APP}" in text          # данные игрока - там же, где их пишет aikit


def test_installer_does_not_ship_portable_marker():
    assert r'Delete "$INSTDIR\portable.txt"' in nsi()


def test_models_folder_is_packed_into_the_build():
    text = open(os.path.join(ROOT, "build.py"), encoding="utf-8").read()
    assert "'game', 'models'" in text and "game/models" in text


def test_icon_is_drawn_in_every_size(tmp_path, qapp):
    Image = pytest.importorskip("PIL.Image")
    path = build.make_icon(str(tmp_path / "icon.ico"))
    with Image.open(path) as ico:
        assert {(16, 16), (32, 32), (256, 256)} <= set(ico.info["sizes"])


def test_trim_moves_away_only_what_the_game_does_not_need(tmp_path):
    root = tmp_path / "dist"
    qt = root / "_internal" / "PySide6"
    (qt / "translations").mkdir(parents=True)
    (qt / "plugins" / "imageformats").mkdir(parents=True)
    keep = [qt / "Qt6Core.dll", qt / "translations" / "qtbase_ru.qm", qt / "plugins" / "imageformats" / "qico.dll"]
    gone = [qt / "opengl32sw.dll", qt / "Qt6Pdf.dll", qt / "translations" / "qtbase_de.qm",
            qt / "plugins" / "imageformats" / "qpdf.dll"]
    for p in keep + gone:
        p.write_bytes(b"12345")
    assert build.trim(str(root), str(tmp_path / "trimmed")) == 5 * len(gone)
    assert all(p.exists() for p in keep)
    assert not any(p.exists() for p in gone)
    assert (tmp_path / "trimmed" / "_internal" / "PySide6" / "Qt6Pdf.dll").exists()   # не удалено, перенесено
