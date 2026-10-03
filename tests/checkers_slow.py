"""Вторая, медленная реализация правил русских шашек - только для сверки в тестах.

Написана по-другому, чем game/core/checkers.py: доска - словарь {(ряд, столбец): фигура}
по всем 64 клеткам, взятие перебирается по одному прыжку с полной копией состояния, без
таблиц лучей. Общее с быстрой - только правила из spec §4 и формат хода (путь, побитые).
"""

WHITE, BLACK = 1, -1


def cells_of(pos_board):
    """Доска быстрой реализации (32 поля) -> словарь по координатам."""
    out = {}
    for s, p in enumerate(pos_board):
        r = s // 4
        c = 2 * (s % 4) + (r % 2)
        out[(r, c)] = p
    return out


def index(r, c):
    return r * 4 + c // 2


def inside(r, c):
    return 0 <= r < 8 and 0 <= c < 8


def is_last_row(side, r):
    return r == 7 if side == WHITE else r == 0


def single_jumps(cells, at, side, king, taken, start):
    """Все одиночные прыжки фигуры из at: [(побитая клетка, клетка приземления)].
    taken - уже побитые в этом ходу (стоят на доске, прыгать через них нельзя),
    start - откуда фигура начала ход (эта клетка пустая)."""
    def empty(rc):
        return rc == start or cells.get(rc, 0) == 0

    found = []
    for dr in (1, -1):
        for dc in (1, -1):
            r, c = at
            if not king:
                o = (r + dr, c + dc)
                land = (r + 2 * dr, c + 2 * dc)
                if inside(*land) and o != start and cells.get(o, 0) * side < 0 and o not in taken and empty(land):
                    found.append((o, land))
                continue
            r, c = r + dr, c + dc
            while inside(r, c) and empty((r, c)):
                r, c = r + dr, c + dc
            if not inside(r, c):
                continue
            o = (r, c)
            if cells[o] * side > 0 or o in taken:
                continue
            r, c = r + dr, c + dc
            while inside(r, c) and empty((r, c)):
                found.append((o, (r, c)))
                r, c = r + dr, c + dc
    return found


def capture_sequences(cells, start, side):
    king0 = abs(cells[start]) == 2
    done = []

    def walk(at, king, taken, path):
        jumps = single_jumps(cells, at, side, king, taken, start)
        if not jumps:
            if taken:
                done.append((tuple(path), tuple(taken)))
            return
        # для каждой побитой - правило дамки: если с какого-то из полей за ней бой идёт
        # дальше, вставать только на такие поля
        by_piece = {}
        for o, land in jumps:
            by_piece.setdefault(o, []).append(land)
        for o, lands in by_piece.items():
            options = []
            for land in lands:
                k2 = king or is_last_row(side, land[0])
                more = single_jumps(cells, land, side, k2, taken + [o], start)
                options.append((land, k2, bool(more)))
            if any(m for _, _, m in options):
                options = [x for x in options if x[2]]
            for land, k2, _ in options:
                walk(land, k2, taken + [o], path + [land])

    walk(start, king0, [], [start])
    return done


def legal_moves(board32, side):
    cells = cells_of(board32)
    caps = []
    for (r, c), p in cells.items():
        if p * side > 0:
            for path, taken in capture_sequences(cells, (r, c), side):
                caps.append((tuple(index(*x) for x in path), tuple(index(*x) for x in taken)))
    if caps:
        uniq = {}
        for m in caps:
            uniq.setdefault((m[0][0], m[0][-1], frozenset(m[1])), m)
        return list(uniq.values())
    moves = []
    for (r, c), p in cells.items():
        if p * side <= 0:
            continue
        if abs(p) == 1:
            for dc in (1, -1):
                t = (r + side, c + dc)
                if inside(*t) and cells[t] == 0:
                    moves.append(((index(r, c), index(*t)), ()))
        else:
            for dr in (1, -1):
                for dc in (1, -1):
                    rr, cc = r + dr, c + dc
                    while inside(rr, cc) and cells[(rr, cc)] == 0:
                        moves.append(((index(r, c), index(rr, cc)), ()))
                        rr, cc = rr + dr, cc + dc
    return moves


def play(board32, side, move):
    b = list(board32)
    path, taken = move
    piece = b[path[0]]
    b[path[0]] = 0
    for t in taken:
        b[t] = 0
    if abs(piece) == 1:
        for s in path[1:]:
            if is_last_row(side, s // 4):
                piece = 2 * side
    b[path[-1]] = piece
    return b


def perft(board32, side, depth):
    if depth == 0:
        return 1
    moves = legal_moves(board32, side)
    if depth == 1:
        return len(moves)
    return sum(perft(play(board32, side, m), -side, depth - 1) for m in moves)
