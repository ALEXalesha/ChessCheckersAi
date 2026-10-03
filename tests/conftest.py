import os
import sys

# Один поток BLAS: проверки паспортов сверяют партии ход в ход, а сумма в другом порядке
# (другое число потоков) может сдвинуть последний знак оценки.
for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(var, "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from aikit import offscreen  # noqa: E402

offscreen.setup()          # без экрана: Qt рисует в память, до любого импорта Qt


@pytest.fixture(autouse=True)
def _own_data_dir(tmp_path, monkeypatch):
    """Каждый тест пишет настройки, статистику и место окна в свою временную папку."""
    home = tmp_path / "home"
    monkeypatch.setenv("CHESSCHECKERSAI_HOME", str(home))
    return home


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
