"""Русские шашки 8x8: доска, ходы, взятия, конец партии. Чистый Python, без Qt.

Доска - 32 тёмных поля, номер s = ряд * 4 + столбец // 2; ряд 0 - первая горизонталь
(сторона белых), a1 - тёмное поле. Значения: 0 пусто, 1 белая простая, 2 белая дамка,
-1 чёрная простая, -2 чёрная дамка. Белые начинают.

Правила (spec §4):
- простая ходит вперёд на одно поле, бьёт вперёд и назад;
- взятие обязательно, вариант любой (не обязательно самый длинный), но начатое взятие
  доводится до конца: остановиться посреди цепочки нельзя;
- побитые шашки снимаются после хода целиком («турецкий удар»): через одну шашку дважды
  не прыгают, и она до конца хода мешает как препятствие;
- дамка ходит и бьёт на любое число полей; после взятия встаёт на любое свободное поле за
  побитой, но если с каких-то из них бой продолжается - только на них;
- простая, дошедшая до последнего ряда во время взятия, сразу дамка и бьёт дальше дамкой;
- нет ходов (или нет шашек) - поражение; ничья - троекратное повторение позиции и 15 ходов
  подряд (30 полуходов) только дамками без взятий.

Ход - кортеж (путь, побитые): путь - поля от начального до конечного, побитые - поля
снятых шашек в порядке взятия. Ходы с одинаковыми началом, концом и набором побитых дают
одну и ту же позицию и считаются одним ходом.
"""
import random

WHITE, BLACK = 1, -1
MAN, KING = 1, 2
QUIET_LIMIT = 30          # 15 ходов каждой стороны только дамками без взятий
DIRS = ((1, -1), (1, 1), (-1, -1), (-1, 1))
FILES = "abcdefgh"


def rc(s):
    r = s // 4
    return r, 2 * (s % 4) + (r % 2)


def sq(r, c):
    """Номер тёмного поля (r, c) или None, если поле светлое или за доской."""
    if 0 <= r < 8 and 0 <= c < 8 and (r + c) % 2 == 0:
        return r * 4 + c // 2
    return None


def name(s):
    r, c = rc(s)
    return f"{FILES[c]}{r + 1}"


def parse_square(text):
    text = text.strip().lower()
    if len(text) != 2 or text[0] not in FILES or not text[1].isdigit():
        raise ValueError(f"нет такого поля: {text!r}")
    s = sq(int(text[1]) - 1, FILES.index(text[0]))
    if s is None:
        raise ValueError(f"поле {text} светлое")
    return s


# Лучи из каждого поля в каждую из четырёх сторон: RAYS[s][d] - поля по порядку.
RAYS = []
for _s in range(32):
    _r, _c = rc(_s)
    _rays = []
    for _dr, _dc in DIRS:
        ray, rr, cc = [], _r + _dr, _c + _dc
        while sq(rr, cc) is not None:
            ray.append(sq(rr, cc))
            rr += _dr
            cc += _dc
        _rays.append(tuple(ray))
    RAYS.append(tuple(_rays))
RAYS = tuple(RAYS)
LAST_ROW = {WHITE: frozenset(range(28, 32)), BLACK: frozenset(range(0, 4))}
FORWARD = {WHITE: (0, 1), BLACK: (2, 3)}           # номера направлений вперёд

# Зобрист: случайное 64-битное число на каждую (поле, фигуру) и на очередь чёрных.
_rnd = random.Random(20261003)
ZOBRIST = [{p: _rnd.getrandbits(64) for p in (1, 2, -1, -2)} for _ in range(32)]
ZOBRIST_BLACK = _rnd.getrandbits(64)


class Position:
    """Позиция: доска, чей ход, счётчик полуходов только дамками без взятий, ключ Зобриста.
    Не меняется - play() возвращает новую."""
    __slots__ = ("board", "turn", "quiet", "key")

    def __init__(self, board, turn=WHITE, quiet=0, key=None):
        self.board = board
        self.turn = turn
        self.quiet = quiet
        self.key = compute_key(board, turn) if key is None else key

    def copy(self):
        return Position(list(self.board), self.turn, self.quiet, self.key)

    def __eq__(self, other):
        return isinstance(other, Position) and self.board == other.board and self.turn == other.turn

    def __hash__(self):
        return self.key

    def __repr__(self):
        return f"Position({to_text(self)!r})"


def compute_key(board, turn):
    k = ZOBRIST_BLACK if turn == BLACK else 0
    for s, p in enumerate(board):
        if p:
            k ^= ZOBRIST[s][p]
    return k


def start():
    board = [0] * 32
    for s in range(12):
        board[s] = WHITE * MAN
    for s in range(20, 32):
        board[s] = BLACK * MAN
    return Position(board, WHITE)


def from_squares(white=(), black=(), white_kings=(), black_kings=(), turn=WHITE, quiet=0):
    """Позиция по спискам полей ('c3', ...) - для ручных позиций в тестах и задачах."""
    board = [0] * 32
    for names, piece in ((white, 1), (black, -1), (white_kings, 2), (black_kings, -2)):
        for n in names:
            board[parse_square(n)] = piece
    return Position(board, turn, quiet)


# --- генератор ходов ---


def _man_captures(board, cur, side, captured, path, out, origin):
    """Продолжения взятия простой из cur. captured - уже побитые (стоят до конца хода)."""
    found = False
    for d in range(4):
        ray = RAYS[cur][d]
        if len(ray) < 2:
            continue
        over, land = ray[0], ray[1]
        p = board[over]
        if p * side < 0 and over not in captured and (board[land] == 0 or land == origin):
            found = True
            cap2 = captured + (over,)
            if land in LAST_ROW[side]:
                # дошла до последнего ряда посреди взятия - дальше бьёт дамкой
                if not _king_captures(board, land, side, cap2, path + (land,), out, origin):
                    out.append((path + (land,), cap2))
            elif not _man_captures(board, land, side, cap2, path + (land,), out, origin):
                out.append((path + (land,), cap2))
    return found


def _king_targets(board, cur, side, captured, origin):
    """Взятия дамки из cur одним прыжком: [(побитое поле, [поля приземления])]."""
    res = []
    for d in range(4):
        ray = RAYS[cur][d]
        i, n = 0, len(ray)
        while i < n and (board[ray[i]] == 0 or ray[i] == origin):
            i += 1
        if i >= n:
            continue
        over = ray[i]
        if board[over] * side > 0 or over in captured:
            continue      # своя шашка или уже побитая: через неё не прыгают («турецкий удар»)
        lands = []
        j = i + 1
        while j < n and (board[ray[j]] == 0 or ray[j] == origin):
            lands.append(ray[j])
            j += 1
        if lands:
            res.append((over, lands))
    return res


def _king_captures(board, cur, side, captured, path, out, origin):
    found = False
    for over, lands in _king_targets(board, cur, side, captured, origin):
        found = True
        cap2 = captured + (over,)
        cont = [lnd for lnd in lands if _king_targets(board, lnd, side, cap2, origin)]
        if cont:
            # бой продолжается - встать можно только туда, откуда он продолжается
            for lnd in cont:
                _king_captures(board, lnd, side, cap2, path + (lnd,), out, origin)
        else:
            for lnd in lands:
                out.append((path + (lnd,), cap2))
    return found


def captures(pos):
    board, side = pos.board, pos.turn
    out = []
    for s in range(32):
        p = board[s]
        if p * side <= 0:
            continue
        if p * side == KING:
            _king_captures(board, s, side, (), (s,), out, s)
        else:
            _man_captures(board, s, side, (), (s,), out, s)
    return _unique(out)


def _unique(moves):
    if len(moves) < 2:
        return moves
    seen, res = set(), []
    for m in moves:
        k = (m[0][0], m[0][-1], frozenset(m[1]))
        if k not in seen:
            seen.add(k)
            res.append(m)
    return res


def quiet_moves(pos):
    board, side = pos.board, pos.turn
    out = []
    fwd = FORWARD[side]
    for s in range(32):
        p = board[s]
        if p * side <= 0:
            continue
        if p * side == KING:
            for d in range(4):
                for t in RAYS[s][d]:
                    if board[t]:
                        break
                    out.append(((s, t), ()))
        else:
            for d in fwd:
                ray = RAYS[s][d]
                if ray and board[ray[0]] == 0:
                    out.append(((s, ray[0]), ()))
    return out


def legal_moves(pos):
    """Все ходы того, чья очередь. Есть взятия - только они."""
    caps = captures(pos)
    return caps if caps else quiet_moves(pos)


def is_capture(move):
    return bool(move[1])


def play(pos, move):
    """Новая позиция после хода (ход не проверяется - он из legal_moves)."""
    path, caps = move
    board = list(pos.board)
    side = pos.turn
    frm, to = path[0], path[-1]
    piece = board[frm]
    key = pos.key ^ ZOBRIST[frm][piece] ^ ZOBRIST_BLACK
    board[frm] = 0
    for c in caps:
        key ^= ZOBRIST[c][board[c]]
        board[c] = 0
    man = abs(piece) == MAN
    if man and any(s in LAST_ROW[side] for s in path[1:]):
        piece = side * KING
    board[to] = piece
    key ^= ZOBRIST[to][piece]
    quiet = 0 if (man or caps) else pos.quiet + 1
    return Position(board, -side, quiet, key)


def promotes(pos, move):
    return abs(pos.board[move[0][0]]) == MAN and any(s in LAST_ROW[pos.turn] for s in move[0][1:])


# --- запись ходов ---


def move_text(move):
    path, caps = move
    sep = ":" if caps else "-"
    return sep.join(name(s) for s in path)


def parse_move(pos, text):
    """Ход по записи 'c3-d4' или 'c3:e5:c7'; короткая запись 'c3:c7' тоже, если она однозначна."""
    parts = [parse_square(t) for t in text.replace("x", ":").replace("-", ":").split(":")]
    fits = [m for m in legal_moves(pos) if m[0][0] == parts[0] and m[0][-1] == parts[-1]
            and (len(parts) == 2 or list(m[0]) == parts)]
    if len(fits) != 1:
        raise ValueError(f"ход {text!r}: {'нет такого' if not fits else 'неоднозначно'}")
    return fits[0]


# --- текст позиции (для тестов и журнала) ---


def to_text(pos):
    """'W:Wc3,Kd4:Be7' - очередь, белые, чёрные; K - дамка. Похоже на FEN шашек PDN."""
    w, b = [], []
    for s, p in enumerate(pos.board):
        if p:
            (w if p > 0 else b).append(("K" if abs(p) == KING else "") + name(s))
    turn = "W" if pos.turn == WHITE else "B"
    return f"{turn}:W{','.join(w)}:B{','.join(b)}"


def from_text(text):
    turn_s, w_s, b_s = text.split(":")
    board = [0] * 32
    for part, side in ((w_s[1:], WHITE), (b_s[1:], BLACK)):
        for item in filter(None, part.split(",")):
            king = item.startswith("K")
            board[parse_square(item[1:] if king else item)] = side * (KING if king else MAN)
    return Position(board, WHITE if turn_s == "W" else BLACK)


# --- партия: история, повторения, конец ---


class Game:
    """Партия с историей: повторения позиций, ничьи, отмена хода."""

    def __init__(self, pos=None):
        self.positions = [pos or start()]
        self.moves = []
        self.counts = {self.positions[0].key: 1}

    @property
    def pos(self):
        return self.positions[-1]

    def legal(self):
        return legal_moves(self.pos)

    def push(self, move):
        nxt = play(self.pos, move)
        self.moves.append(move)
        self.positions.append(nxt)
        self.counts[nxt.key] = self.counts.get(nxt.key, 0) + 1
        return nxt

    def pop(self):
        if not self.moves:
            return None
        last = self.positions.pop()
        self.counts[last.key] -= 1
        return self.moves.pop()

    def result(self):
        """None - партия идёт; иначе (исход для белых 1/0/-1, причина)."""
        pos = self.pos
        if not legal_moves(pos):
            reason = "no_pieces" if not any(p * pos.turn > 0 for p in pos.board) else "no_moves"
            return (-pos.turn, reason)
        if self.counts.get(pos.key, 0) >= 3:
            return (0, "repetition")
        if pos.quiet >= QUIET_LIMIT:
            return (0, "kings_only")
        return None


def perft(pos, depth):
    if depth == 0:
        return 1
    moves = legal_moves(pos)
    if depth == 1:
        return len(moves)
    return sum(perft(play(pos, m), depth - 1) for m in moves)
