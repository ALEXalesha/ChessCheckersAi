"""python -m game.train --game checkers|chess ... (см. game/train/selfplay.py).

Потоки BLAS ограничиваются здесь, до импорта numpy: обучение делит процессор с другими
программами. Работники самоигры - отдельные процессы по одному потоку (--threads).
"""
import sys

from aikit import trainlog

trainlog.limit_threads(1)

from game.train.selfplay import main  # noqa: E402

sys.exit(main())
