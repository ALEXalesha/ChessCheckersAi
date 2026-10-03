"""Поиск хода сети и «Мысли сети» в отдельном потоке: окно не подвисает.

Каждый запрос получает номер (token). Ответ со старым номером (партию отменили, ход
отменили, вышли в меню) выбрасывается. Остановка - флагом: поиск проверяет его каждые
16 узлов и выходит; при закрытии окна поток ждут не дольше 2 секунд (контракт aikit).
"""
import threading

from PySide6.QtCore import QObject, QThread, Signal

from game.ai import games, models
from game.ai.search import MATE, Searcher


class _Job(QThread):
    done = Signal(int, str, object)

    def __init__(self, token, kind, fn, parent=None):
        super().__init__(parent)
        self.token = token
        self.kind = kind
        self.fn = fn
        self.stop_event = threading.Event()

    def run(self):
        try:
            payload = self.fn(self.stop_event.is_set)
        except Exception as e:  # noqa: BLE001 - ошибку покажет окно, поток не должен падать молча
            payload = e
        if not self.stop_event.is_set():
            self.done.emit(self.token, self.kind, payload)


class AiController(QObject):
    """Ход сети: request_move; оценки ходов: request_thoughts. Ответ - сигнал ready."""

    ready = Signal(int, str, object)       # номер, 'move' | 'thoughts', результат или ошибка

    THOUGHT_DEPTH = {"checkers": 2, "chess": 1}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs = []
        self._evals = {}

    def evaluator(self, kind, level):
        """Сеть уровня или, если модели нет, оценка по материалу (видно в окне)."""
        key = (kind, level)
        if key not in self._evals:
            if models.has_model(kind):
                self._evals[key] = (games.net_eval(kind, level), True)
            else:
                self._evals[key] = (games.material(kind), False)
        return self._evals[key]

    def has_net(self, kind):
        return models.has_model(kind)

    def _start(self, token, kind, fn):
        self._reap()
        job = _Job(token, kind, fn, self)
        job.done.connect(self.ready)
        self.jobs.append(job)
        job.start()
        return job

    def _reap(self):
        self.jobs = [j for j in self.jobs if j.isRunning()]

    def request_move(self, token, session, max_time=None, depth=None):
        kind, level = session.kind, session.level
        evaluate, _ = self.evaluator(kind, level)
        pos = session.pos
        history = session.history_keys()
        depth = depth or games.LEVEL_DEPTH[kind][level]
        max_time = games.LEVEL_TIME[level] if max_time is None else max_time

        def fn(stop):
            s = Searcher(games.adapter(kind), evaluate)
            return s.search(pos, depth=depth, max_time=max_time, stop=stop, history=history)
        return self._start(token, "move", fn)

    def request_thoughts(self, token, session):
        kind, level = session.kind, session.level
        evaluate, _ = self.evaluator(kind, level)
        pos = session.pos
        history = session.history_keys()

        def fn(stop):
            s = Searcher(games.adapter(kind), evaluate)
            scores = s.analyse(pos, depth=self.THOUGHT_DEPTH[kind], history=history, stop=stop)
            return {m: (1.0 if v > MATE - 1 else -1.0 if v < -(MATE - 1) else v) for m, v in scores.items()}
        return self._start(token, "thoughts", fn)

    def cancel(self):
        for j in self.jobs:
            j.stop_event.set()

    def busy(self):
        self._reap()
        return bool(self.jobs)

    def shutdown(self, timeout_ms=2000):
        """Остановить все поиски и дождаться потоков (не дольше timeout_ms на всё)."""
        import time
        self.cancel()
        deadline = time.monotonic() + timeout_ms / 1000
        for j in self.jobs:
            left = max(0, int((deadline - time.monotonic()) * 1000))
            j.wait(left)
        self._reap()
        return not self.jobs
