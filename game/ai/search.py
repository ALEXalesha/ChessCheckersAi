"""Поиск хода, общий для шашек и шахмат: альфа-бета (negamax) с итеративным углублением,
таблицей перестановок по ключу Зобриста, порядком ходов, тихим поиском, лимитом времени
и остановкой по флагу.

Игру описывает адаптер (game/ai/adapters.py):
    moves(pos)          все ходы того, чья очередь
    play(pos, m)        новая позиция
    key(pos)            ключ Зобриста
    rule_draw(pos)      ничья по правилу, видная из самой позиции (50 ходов, дамки, материал)
    no_moves_score(pos) оценка позиции без ходов для того, чья очередь (-MATE или 0 - пат)
    qmoves(pos)         (ходы тихого поиска, можно ли стоять): шашки - обязательные взятия,
                        шахматы - взятия и превращения, под шахом - все ходы
    noisy(pos, m)       взятие или превращение - такие ходы идут первыми
    order_key(pos, m)   чем больше, тем раньше среди взятий (MVV-LVA и т. п.)

Оценка - функция evaluate(список позиций) -> массив чисел в (-1, 1) с точки зрения того,
кто только что сходил в каждой позиции: так сеть оценивает позицию после хода. Узел глубины
1 оценивает всех своих детей одним вызовом - для сети это один проход numpy на пачку.

Оценки внутри поиска - с точки зрения того, чья очередь в узле. Мат - MATE минус число
полуходов до него: ближний мат лучше дальнего.
"""
import time

import numpy as np

MATE = 10.0
INF = 1e9
EXACT, LOWER, UPPER = 0, 1, 2
QDEPTH = 12                 # предел тихого поиска в полуходах


class Stopped(Exception):
    pass


class Result:
    __slots__ = ("move", "score", "depth", "nodes", "leaf", "pv", "seconds", "root_scores")

    def __init__(self, move, score, depth, nodes, leaf, pv, seconds, root_scores=None):
        self.move, self.score, self.depth, self.nodes = move, score, depth, nodes
        self.leaf, self.pv, self.seconds = leaf, pv, seconds
        self.root_scores = root_scores or {}

    def __repr__(self):
        return f"Result(score={self.score:.3f}, depth={self.depth}, nodes={self.nodes})"


class Searcher:
    """Один поиск - один объект или повторное использование: таблица перестановок
    остаётся между ходами партии (clear() - начать с чистой)."""

    def __init__(self, adapter, evaluate, tt_size=400_000, rng=None, quiescence=True):
        self.ad = adapter
        self.evaluate = evaluate
        self.tt = {}
        self.tt_size = tt_size
        self.rng = rng
        self.quiescence = quiescence
        self.nodes = 0
        self.deadline = None
        self.stop_flag = None
        self.history = frozenset()

    def clear(self):
        self.tt.clear()

    # --- служебное ---

    def _check(self):
        self.nodes += 1
        if self.nodes & 15 == 0:
            if self.stop_flag is not None and self.stop_flag():
                raise Stopped
            if self.deadline is not None and time.perf_counter() > self.deadline:
                raise Stopped

    def _children_values(self, pos, moves):
        children = [self.ad.play(pos, m) for m in moves]
        if not children:
            return children, np.zeros(0)
        return children, np.asarray(self.evaluate(children), dtype=np.float64)

    def _ordered(self, pos, moves, depth, tt_move, ply):
        """Порядок: ход из таблицы, взятия (по order_key), остальные - по оценке после хода."""
        ad = self.ad
        if ply == 0 and self.rng is not None:
            moves = list(moves)
            self.rng.shuffle(moves)        # равные ходы ботов - в случайном порядке
        children, vals = self._children_values(pos, moves)
        keyed = []
        for i, m in enumerate(moves):
            if m == tt_move:
                k = 1e6
            elif ad.noisy(pos, m):
                k = 1e3 + ad.order_key(pos, m)
            else:
                k = vals[i]
            keyed.append((k, i))
        keyed.sort(key=lambda t: -t[0])
        return [(moves[i], children[i], vals[i]) for _, i in keyed]

    # --- поиск ---

    def search(self, pos, depth=None, max_time=None, stop=None, history=(), min_depth=1):
        """Лучший ход для того, чья очередь. depth - предел глубины (None - пока есть
        время), max_time - секунды, stop - функция без аргументов, True - остановиться.
        history - ключи позиций партии до pos (для повторений). Глубина min_depth
        дорабатывается даже после лимита времени, чтобы был ход."""
        started = time.perf_counter()
        self.nodes = 0
        self.stop_flag = stop
        self.history = frozenset(history)
        moves = self.ad.moves(pos)
        if not moves:
            return Result(None, self.ad.no_moves_score(pos), 0, 0, pos, [], 0.0)
        best = None
        limit = depth if depth is not None else 64
        for d in range(1, limit + 1):
            self.deadline = None if (max_time is None or d <= min_depth) else started + max_time
            try:
                score, move, leaf, pv, root_scores = self._root(pos, d)
            except Stopped:
                break
            best = Result(move, score, d, self.nodes, leaf, pv, time.perf_counter() - started, root_scores)
            if abs(score) > MATE - 1:
                break                        # мат найден - глубже искать незачем
            if max_time is not None and time.perf_counter() - started > max_time * 0.5:
                break                        # следующая глубина не успеет
        if best is None:                     # не успела даже первая глубина
            m = moves[0]
            best = Result(m, 0.0, 0, self.nodes, self.ad.play(pos, m), [m], time.perf_counter() - started)
        best.nodes = self.nodes
        best.seconds = time.perf_counter() - started
        return best

    def _root(self, pos, depth):
        entry = self.tt.get(self.ad.key(pos))
        tt_move = entry[3] if entry else None
        alpha, beta = -INF, INF
        best_move, best_leaf, best_pv = None, pos, []
        root_scores = {}
        path = {self.ad.key(pos)}
        for m, child, v in self._ordered(pos, self.ad.moves(pos), depth, tt_move, 0):
            score, leaf, pv = self._child(child, v, depth - 1, -beta, -alpha, 1, path)
            score = -score
            root_scores[m] = score
            if score > alpha or best_move is None:
                alpha = score if score > alpha else alpha
                best_move, best_leaf, best_pv = m, leaf, [m] + pv
        self._store(pos, depth, alpha, EXACT, best_move)
        return alpha, best_move, best_leaf, best_pv, root_scores

    def _child(self, child, value, depth, alpha, beta, ply, path):
        """Оценка ребёнка с точки зрения того, чья очередь в нём. value - оценка ребёнка
        сетью с точки зрения сходившего (уже посчитана пачкой у родителя)."""
        k = self.ad.key(child)
        if k in path or k in self.history:
            return 0.0, child, []            # повторение - ничья
        if self.ad.rule_draw(child):
            return 0.0, child, []
        if depth <= 0:
            return self._quiesce(child, -value, alpha, beta, ply, 0, path)
        return self._negamax(child, depth, alpha, beta, ply, path)

    def _negamax(self, pos, depth, alpha, beta, ply, path):
        self._check()
        key = self.ad.key(pos)
        entry = self.tt.get(key)
        tt_move = None
        if entry is not None:
            e_depth, e_score, e_flag, tt_move = entry
            if e_depth >= depth:
                if e_flag == EXACT:
                    return e_score, pos, []
                if e_flag == LOWER and e_score >= beta:
                    return e_score, pos, []
                if e_flag == UPPER and e_score <= alpha:
                    return e_score, pos, []
        moves = self.ad.moves(pos)
        if not moves:
            s = self.ad.no_moves_score(pos)
            return (s + ply * 0.01 if s < 0 else s), pos, []
        alpha0 = alpha
        best, best_move, best_leaf, best_pv = -INF, None, pos, []
        path.add(key)
        try:
            for m, child, v in self._ordered(pos, moves, depth, tt_move, ply):
                score, leaf, pv = self._child(child, v, depth - 1, -beta, -alpha, ply + 1, path)
                score = -score
                if score > best:
                    best, best_move, best_leaf, best_pv = score, m, leaf, [m] + pv
                if score > alpha:
                    alpha = score
                if alpha >= beta:
                    break
        finally:
            path.discard(key)
        flag = UPPER if best <= alpha0 else (LOWER if best >= beta else EXACT)
        self._store(pos, depth, best, flag, best_move)
        return best, best_leaf, best_pv

    def _quiesce(self, pos, stand, alpha, beta, ply, qply, path):
        """Тихий поиск: доиграть взятия, чтобы не оценивать позицию посреди размена.
        stand - оценка самой позиции для того, чья очередь."""
        self._check()
        if not self.quiescence or qply >= QDEPTH:
            return stand, pos, []
        moves, can_stand = self.ad.qmoves(pos)
        if can_stand:
            if stand >= beta or not moves:
                return stand, pos, []
            best, best_leaf, best_pv = stand, pos, []
            if stand > alpha:
                alpha = stand
        else:
            if not moves:
                s = self.ad.no_moves_score(pos)
                return (s + ply * 0.01 if s < 0 else s), pos, []
            best, best_leaf, best_pv = -INF, pos, []
        key = self.ad.key(pos)
        path.add(key)
        try:
            children, vals = self._children_values(pos, moves)
            order = sorted(range(len(moves)), key=lambda i: -(self.ad.order_key(pos, moves[i]) * 10 + vals[i]))
            for i in order:
                child = children[i]
                ck = self.ad.key(child)
                if ck in path or ck in self.history or self.ad.rule_draw(child):
                    score, leaf, pv = 0.0, child, []
                else:
                    score, leaf, pv = self._quiesce(child, -vals[i], -beta, -alpha, ply + 1, qply + 1, path)
                score = -score
                if score > best:
                    best, best_leaf, best_pv = score, leaf, [moves[i]] + pv
                if score > alpha:
                    alpha = score
                if alpha >= beta:
                    break
        finally:
            path.discard(key)
        return best, best_leaf, best_pv

    def _store(self, pos, depth, score, flag, move):
        if len(self.tt) >= self.tt_size:
            self.tt.clear()
        self.tt[self.ad.key(pos)] = (depth, score, flag, move)

    # --- оценка каждого хода (для «Мыслей сети») ---

    def analyse(self, pos, depth=1, history=(), stop=None):
        """{ход: оценка для того, чья очередь} - каждый ход своим полным окном, не только лучший."""
        self.stop_flag = stop
        self.deadline = None
        self.history = frozenset(history)
        self.nodes = 0
        out = {}
        path = {self.ad.key(pos)}
        for m, child, v in self._ordered(pos, self.ad.moves(pos), depth, None, 1):
            score, _, _ = self._child(child, v, depth - 1, -INF, INF, 1, path)
            out[m] = -score
        return out


def minimax(adapter, evaluate, pos, depth, ply=0, path=None):
    """Полный минимакс без отсечений и без таблицы - эталон для тестов поиска (малая глубина).
    Те же правила листьев, что у Searcher без тихого поиска: повтор позиции на пути - ничья."""
    path = set() if path is None else path
    if depth == 0:
        # оценка узла для того, чья очередь = минус оценка сходившего
        return -float(evaluate([pos])[0])
    moves = adapter.moves(pos)
    if not moves:
        s = adapter.no_moves_score(pos)
        return s + ply * 0.01 if s < 0 else s
    best = -INF
    path.add(adapter.key(pos))
    for m in moves:
        child = adapter.play(pos, m)
        if adapter.key(child) in path or adapter.rule_draw(child):
            s = 0.0
        else:
            s = -minimax(adapter, evaluate, child, depth - 1, ply + 1, path)
        best = max(best, s)
    path.discard(adapter.key(pos))
    return best
