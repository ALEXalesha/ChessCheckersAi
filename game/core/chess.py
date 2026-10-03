"""Шахматы: все правила, SAN, FEN, PGN. Чистый Python, без Qt.

Доска - массив 10x12 (120 клеток): поле a1 = 21, h1 = 28, a8 = 91, h8 = 98, вокруг - две
полосы клеток OFF, чтобы ход коня или луча за край сразу упирался в границу. Фигуры:
1 пешка, 2 конь, 3 слон, 4 ладья, 5 ферзь, 6 король; белые > 0, чёрные < 0.

Ход - кортеж (откуда, куда, превращение, признак): превращение 0 или 2..5, признак - 0,
EP (взятие на проходе), CASTLE (рокировка), DOUBLE (пешка на два поля).

Генератор: сначала ходы по правилам движения фигур, потом каждый проверяется - не остался
ли свой король под боем (ход делается прямо на доске и сразу откатывается). Рокировка:
король не под шахом, поле, через которое он идёт, и конечное - не под боем.

Ничьи (spec §4): правило 50 ходов, троекратное повторение, недостаточно материала, пат.
"""
import random

WHITE, BLACK = 1, -1
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = 1, 2, 3, 4, 5, 6
OFF = 7
EP, CASTLE, DOUBLE = 1, 2, 4
WK, WQ, BK, BQ = 1, 2, 4, 8
FILES = "abcdefgh"
PIECE_LETTERS = {PAWN: "P", KNIGHT: "N", BISHOP: "B", ROOK: "R", QUEEN: "Q", KING: "K"}
LETTER_PIECE = {v: k for k, v in PIECE_LETTERS.items()}
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

N_STEPS = (-21, -19, -12, -8, 8, 12, 19, 21)
K_STEPS = (-11, -10, -9, -1, 1, 9, 10, 11)
B_DIRS = (-11, -9, 9, 11)
R_DIRS = (-10, -1, 1, 10)
Q_DIRS = B_DIRS + R_DIRS
VALUES = {PAWN: 1, KNIGHT: 3, BISHOP: 3, ROOK: 5, QUEEN: 9, KING: 0}

# Права на рокировку теряются, когда с поля уходит или на нём бьют: король или ладья.
CASTLE_MASK = [15] * 120
CASTLE_MASK[25] = 15 & ~(WK | WQ)
CASTLE_MASK[21] = 15 & ~WQ
CASTLE_MASK[28] = 15 & ~WK
CASTLE_MASK[95] = 15 & ~(BK | BQ)
CASTLE_MASK[91] = 15 & ~BQ
CASTLE_MASK[98] = 15 & ~BK

SQUARES = tuple(21 + r * 10 + c for r in range(8) for c in range(8))


def rc(sq):
    """(ряд 0..7 от белых, столбец 0..7) поля sq (в 120-клеточной раскладке)."""
    return sq // 10 - 2, sq % 10 - 1


def sq_of(r, c):
    return 21 + r * 10 + c


def name(sq):
    r, c = rc(sq)
    return f"{FILES[c]}{r + 1}"


def parse_square(text):
    if len(text) != 2 or text[0] not in FILES or text[1] not in "12345678":
        raise ValueError(f"нет такого поля: {text!r}")
    return sq_of(int(text[1]) - 1, FILES.index(text[0]))


_rnd = random.Random(19700101)
Z_PIECE = {p: [_rnd.getrandbits(64) for _ in range(120)] for p in (1, 2, 3, 4, 5, 6, -1, -2, -3, -4, -5, -6)}
Z_CASTLE = [_rnd.getrandbits(64) for _ in range(16)]
Z_EP = [_rnd.getrandbits(64) for _ in range(8)]
Z_BLACK = _rnd.getrandbits(64)


class Position:
    """Позиция; play() возвращает новую. ep - поле взятия на проходе, только если чужая
    пешка стоит рядом и может туда бить (так одинаковые позиции считаются одинаковыми при
    повторениях)."""
    __slots__ = ("board", "turn", "castling", "ep", "halfmove", "fullmove", "kings", "key")

    def __init__(self, board, turn, castling, ep, halfmove, fullmove, kings=None, key=None):
        self.board = board
        self.turn = turn
        self.castling = castling
        self.ep = ep
        self.halfmove = halfmove
        self.fullmove = fullmove
        if kings is None:
            kings = {WHITE: board.index(KING) if KING in board else None,
                     BLACK: board.index(-KING) if -KING in board else None}
        self.kings = kings
        self.key = compute_key(self) if key is None else key

    def pieces(self):
        b = self.board
        for sq in SQUARES:
            if b[sq]:
                yield sq, b[sq]

    def __eq__(self, other):
        return (isinstance(other, Position) and self.board == other.board and self.turn == other.turn
                and self.castling == other.castling and self.ep == other.ep)

    def __hash__(self):
        return self.key

    def __repr__(self):
        return f"Position({to_fen(self)!r})"


def compute_key(pos):
    k = Z_BLACK if pos.turn == BLACK else 0
    for sq, p in pos.pieces():
        k ^= Z_PIECE[p][sq]
    k ^= Z_CASTLE[pos.castling]
    if pos.ep is not None:
        k ^= Z_EP[pos.ep % 10 - 1]
    return k


def empty_board():
    b = [OFF] * 120
    for sq in SQUARES:
        b[sq] = 0
    return b


# --- FEN ---


def from_fen(fen):
    parts = fen.split()
    if len(parts) < 4:
        raise ValueError(f"плохой FEN: {fen!r}")
    rows = parts[0].split("/")
    if len(rows) != 8:
        raise ValueError(f"плохой FEN: {fen!r}")
    b = empty_board()
    for i, row in enumerate(rows):
        r = 7 - i
        c = 0
        for ch in row:
            if ch.isdigit():
                c += int(ch)
            else:
                p = LETTER_PIECE.get(ch.upper())
                if p is None or c > 7:
                    raise ValueError(f"плохой FEN: {fen!r}")
                b[sq_of(r, c)] = p if ch.isupper() else -p
                c += 1
        if c != 8:
            raise ValueError(f"плохой FEN: {fen!r}")
    turn = WHITE if parts[1] == "w" else BLACK
    castling = 0
    for ch, bit in (("K", WK), ("Q", WQ), ("k", BK), ("q", BQ)):
        if ch in parts[2]:
            castling |= bit
    ep = None if parts[3] == "-" else parse_square(parts[3])
    half = int(parts[4]) if len(parts) > 4 else 0
    full = int(parts[5]) if len(parts) > 5 else 1
    pos = Position(b, turn, castling, None, half, full)
    if ep is not None and _ep_possible(b, ep, turn):
        pos = Position(b, turn, castling, ep, half, full)
    return pos


def to_fen(pos):
    rows = []
    for r in range(7, -1, -1):
        row, run = "", 0
        for c in range(8):
            p = pos.board[sq_of(r, c)]
            if p == 0:
                run += 1
                continue
            if run:
                row += str(run)
                run = 0
            ch = PIECE_LETTERS[abs(p)]
            row += ch if p > 0 else ch.lower()
        rows.append(row + (str(run) if run else ""))
    cast = "".join(ch for ch, bit in (("K", WK), ("Q", WQ), ("k", BK), ("q", BQ)) if pos.castling & bit) or "-"
    ep = name(pos.ep) if pos.ep is not None else "-"
    return f"{'/'.join(rows)} {'w' if pos.turn == WHITE else 'b'} {cast} {ep} {pos.halfmove} {pos.fullmove}"


def start():
    return from_fen(START_FEN)


def _ep_possible(b, ep, turn):
    """Есть ли у того, чья очередь (turn), пешка, которая может бить на поле ep."""
    pawn_from = ep - 10 * turn
    return b[pawn_from - 1] == turn * PAWN or b[pawn_from + 1] == turn * PAWN


# --- атаки ---


def attacked(b, sq, by):
    """Бьёт ли сторона by поле sq."""
    # пешки: белая пешка бьёт вверх, значит на поле sq её надо искать снизу
    p = by * PAWN
    if by == WHITE:
        if b[sq - 9] == p or b[sq - 11] == p:
            return True
    elif b[sq + 9] == p or b[sq + 11] == p:
        return True
    n = by * KNIGHT
    for d in N_STEPS:
        if b[sq + d] == n:
            return True
    k = by * KING
    for d in K_STEPS:
        if b[sq + d] == k:
            return True
    bq, rq = (by * BISHOP, by * QUEEN), (by * ROOK, by * QUEEN)
    for d in B_DIRS:
        t = sq + d
        while b[t] == 0:
            t += d
        if b[t] in bq:
            return True
    for d in R_DIRS:
        t = sq + d
        while b[t] == 0:
            t += d
        if b[t] in rq:
            return True
    return False


def in_check(pos, side=None):
    side = pos.turn if side is None else side
    k = pos.kings[side]
    return k is not None and attacked(pos.board, k, -side)


# --- генератор ---


def pseudo_moves(pos, captures_only=False):
    b, side = pos.board, pos.turn
    out = []
    add = out.append
    up = 10 * side
    start_row, promo_row = (1, 7) if side == WHITE else (6, 0)
    for sq in SQUARES:
        p = b[sq] * side
        if p <= 0:
            continue
        if p == PAWN:
            r = sq // 10 - 2
            t = sq + up
            for cap in (t - 1, t + 1):
                q = b[cap]
                if q != OFF and q * side < 0:
                    if r + side == promo_row:
                        for pr in (QUEEN, ROOK, BISHOP, KNIGHT):
                            add((sq, cap, pr, 0))
                    else:
                        add((sq, cap, 0, 0))
                elif cap == pos.ep:
                    add((sq, cap, 0, EP))
            if b[t] == 0:
                if r + side == promo_row:
                    for pr in (QUEEN, ROOK, BISHOP, KNIGHT):
                        add((sq, t, pr, 0))
                elif not captures_only:
                    add((sq, t, 0, 0))
                    if r == start_row and b[t + up] == 0:
                        add((sq, t + up, 0, DOUBLE))
        elif p == KNIGHT or p == KING:
            for d in (N_STEPS if p == KNIGHT else K_STEPS):
                t = sq + d
                q = b[t]
                if q == 0:
                    if not captures_only:
                        add((sq, t, 0, 0))
                elif q != OFF and q * side < 0:
                    add((sq, t, 0, 0))
        else:
            for d in (B_DIRS if p == BISHOP else R_DIRS if p == ROOK else Q_DIRS):
                t = sq + d
                while b[t] == 0:
                    if not captures_only:
                        add((sq, t, 0, 0))
                    t += d
                q = b[t]
                if q != OFF and q * side < 0:
                    add((sq, t, 0, 0))
    if not captures_only:
        _castles(pos, add)
    return out


def _castles(pos, add):
    b, side, cr = pos.board, pos.turn, pos.castling
    if side == WHITE:
        k, kbit, qbit = 25, WK, WQ
    else:
        k, kbit, qbit = 95, BK, BQ
    if not cr & (kbit | qbit) or b[k] != side * KING:
        return
    if attacked(b, k, -side):
        return
    if cr & kbit and b[k + 1] == 0 and b[k + 2] == 0 and b[k + 3] == side * ROOK \
            and not attacked(b, k + 1, -side) and not attacked(b, k + 2, -side):
        add((k, k + 2, 0, CASTLE))
    if cr & qbit and b[k - 1] == 0 and b[k - 2] == 0 and b[k - 3] == 0 and b[k - 4] == side * ROOK \
            and not attacked(b, k - 1, -side) and not attacked(b, k - 2, -side):
        add((k, k - 2, 0, CASTLE))


def _leaves_king_safe(pos, m):
    b, side = pos.board, pos.turn
    frm, to, _, flag = m
    piece = b[frm]
    captured = b[to]
    b[to] = piece
    b[frm] = 0
    cap_sq = None
    if flag == EP:
        cap_sq = to - 10 * side
        cap_piece = b[cap_sq]
        b[cap_sq] = 0
    ksq = to if piece == side * KING else pos.kings[side]
    safe = ksq is None or not attacked(b, ksq, -side)
    b[frm] = piece
    b[to] = captured
    if cap_sq is not None:
        b[cap_sq] = cap_piece
    return safe


def legal_moves(pos):
    return [m for m in pseudo_moves(pos) if _leaves_king_safe(pos, m)]


def legal_captures(pos):
    """Взятия и превращения (для тихого поиска)."""
    return [m for m in pseudo_moves(pos, captures_only=True) if _leaves_king_safe(pos, m)]


def is_capture(pos, m):
    return m[3] == EP or pos.board[m[1]] != 0


def play(pos, m):
    frm, to, promo, flag = m
    b = list(pos.board)
    side = pos.turn
    piece = b[frm]
    captured = b[to]
    key = pos.key ^ Z_PIECE[piece][frm] ^ Z_BLACK ^ Z_CASTLE[pos.castling]
    if pos.ep is not None:
        key ^= Z_EP[pos.ep % 10 - 1]
    if captured:
        key ^= Z_PIECE[captured][to]
    b[frm] = 0
    new_piece = side * promo if promo else piece
    b[to] = new_piece
    key ^= Z_PIECE[new_piece][to]
    kings = pos.kings
    if flag == EP:
        cap_sq = to - 10 * side
        key ^= Z_PIECE[b[cap_sq]][cap_sq]
        b[cap_sq] = 0
        captured = -side * PAWN
    elif flag == CASTLE:
        if to > frm:
            rf, rt = frm + 3, frm + 1
        else:
            rf, rt = frm - 4, frm - 1
        rook = b[rf]
        b[rf] = 0
        b[rt] = rook
        key ^= Z_PIECE[rook][rf] ^ Z_PIECE[rook][rt]
    if abs(piece) == KING:
        kings = dict(kings)
        kings[side] = to
    castling = pos.castling & CASTLE_MASK[frm] & CASTLE_MASK[to]
    key ^= Z_CASTLE[castling]
    ep = None
    if flag == DOUBLE:
        e = frm + 10 * side
        if _ep_possible(b, e, -side):
            ep = e
            key ^= Z_EP[e % 10 - 1]
    half = 0 if (abs(piece) == PAWN or captured) else pos.halfmove + 1
    full = pos.fullmove + (1 if side == BLACK else 0)
    return Position(b, -side, castling, ep, half, full, kings, key)


def perft(pos, depth):
    moves = legal_moves(pos)
    if depth <= 1:
        return len(moves) if depth == 1 else 1
    return sum(perft(play(pos, m), depth - 1) for m in moves)


# --- конец партии ---


def insufficient_material(pos):
    """Ни одна сторона не может поставить мат: король против короля, король и лёгкая фигура
    против короля, короли и слоны одного цвета полей."""
    minors = []
    for sq, p in pos.pieces():
        a = abs(p)
        if a == KING:
            continue
        if a in (PAWN, ROOK, QUEEN):
            return False
        minors.append((a, sq))
    if len(minors) <= 1:
        return True
    if all(a == BISHOP for a, _ in minors):
        colors = {sum(rc(sq)) % 2 for _, sq in minors}
        return len(colors) == 1
    return False


class Game:
    """Партия с историей: повторения, ничьи, отмена хода, запись SAN."""

    def __init__(self, pos=None, tags=None):
        self.positions = [pos or start()]
        self.moves = []
        self.sans = []
        self.counts = {self.positions[0].key: 1}
        self.tags = dict(tags or {})

    @property
    def pos(self):
        return self.positions[-1]

    def legal(self):
        return legal_moves(self.pos)

    def push(self, move):
        self.sans.append(san(self.pos, move))
        nxt = play(self.pos, move)
        self.moves.append(move)
        self.positions.append(nxt)
        self.counts[nxt.key] = self.counts.get(nxt.key, 0) + 1
        return nxt

    def push_san(self, text):
        return self.push(parse_san(self.pos, text))

    def pop(self):
        if not self.moves:
            return None
        last = self.positions.pop()
        self.counts[last.key] -= 1
        self.sans.pop()
        return self.moves.pop()

    def result(self):
        """None - партия идёт; иначе (исход для белых 1/0/-1, причина)."""
        pos = self.pos
        if not legal_moves(pos):
            if in_check(pos):
                return (-pos.turn, "checkmate")
            return (0, "stalemate")
        if self.counts.get(pos.key, 0) >= 3:
            return (0, "repetition")
        if pos.halfmove >= 100:
            return (0, "fifty")
        if insufficient_material(pos):
            return (0, "material")
        return None


# --- SAN ---


def san(pos, m):
    """Запись хода в алгебраической нотации: Nf3, exd5, O-O, e8=Q+, Qh4#."""
    frm, to, promo, flag = m
    piece = abs(pos.board[frm])
    if flag == CASTLE:
        text = "O-O" if to > frm else "O-O-O"
    else:
        capture = is_capture(pos, m)
        if piece == PAWN:
            text = (FILES[rc(frm)[1]] + "x" if capture else "") + name(to)
            if promo:
                text += "=" + PIECE_LETTERS[promo]
        else:
            text = PIECE_LETTERS[piece]
            rivals = [o for o in legal_moves(pos) if o[1] == to and o[0] != frm and abs(pos.board[o[0]]) == piece]
            if rivals:
                fr, fc = rc(frm)
                same_file = any(rc(o[0])[1] == fc for o in rivals)
                same_rank = any(rc(o[0])[0] == fr for o in rivals)
                if not same_file:
                    text += FILES[fc]
                elif not same_rank:
                    text += str(fr + 1)
                else:
                    text += name(frm)
            text += ("x" if capture else "") + name(to)
    after = play(pos, m)
    if in_check(after):
        text += "#" if not legal_moves(after) else "+"
    return text


def parse_san(pos, text):
    """Ход по записи SAN (с + # ! ? или без). Неверная или неоднозначная запись - ValueError."""
    t = text.strip().rstrip("+#!?").replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    moves = legal_moves(pos)
    if t in ("O-O", "O-O-O"):
        for m in moves:
            if m[3] == CASTLE and (m[1] > m[0]) == (t == "O-O"):
                return m
        raise ValueError(f"ход {text!r} невозможен в позиции {to_fen(pos)}")
    # SAN считается только у ходов на нужное поле - иначе разбор партии квадратичный
    for m in moves:
        if name(m[1]) in t and san(pos, m).rstrip("+#") == t:
            return m
    # мягче: без «x», с полем откуда (Ng1f3), превращение без «=»
    loose = t.replace("x", "").replace("=", "")
    found = []
    for m in moves:
        frm, to, promo, flag = m
        piece = abs(pos.board[frm])
        full = ("" if piece == PAWN else PIECE_LETTERS[piece]) + name(frm) + name(to) +             (PIECE_LETTERS[promo] if promo else "")
        if loose == full or loose == full.lower():
            found.append(m)
    if len(found) == 1:
        return found[0]
    raise ValueError(f"ход {text!r} невозможен в позиции {to_fen(pos)}")


def uci(m):
    return name(m[0]) + name(m[1]) + ("nbrq"[m[2] - 2] if m[2] else "")


def parse_uci(pos, text):
    for m in legal_moves(pos):
        if uci(m) == text:
            return m
    raise ValueError(f"ход {text!r} невозможен")


# --- PGN ---

RESULT_TEXT = {1: "1-0", -1: "0-1", 0: "1/2-1/2"}


def to_pgn(game, tags=None):
    tags = {"Event": "ChessCheckersAi", "Site": "?", "Date": "????.??.??", "Round": "-",
            "White": "?", "Black": "?", **game.tags, **(tags or {})}
    res = game.result()
    tags["Result"] = RESULT_TEXT[res[0]] if res else tags.get("Result", "*")
    if game.positions[0] != start() or game.positions[0].fullmove != 1:
        tags["SetUp"] = "1"
        tags["FEN"] = to_fen(game.positions[0])
    head = "".join(f'[{k} "{v}"]\n' for k, v in tags.items())
    words = []
    pos0 = game.positions[0]
    num, black = pos0.fullmove, pos0.turn == BLACK
    for i, s in enumerate(game.sans):
        if not black:
            words.append(f"{num}.")
        elif i == 0:
            words.append(f"{num}...")
        words.append(s)
        if black:
            num += 1
        black = not black
    words.append(tags["Result"])
    lines, line = [], ""
    for w in words:
        if len(line) + len(w) + 1 > 79:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}" if line else w
    lines.append(line)
    return head + "\n" + "\n".join(lines) + "\n"


def from_pgn(text):
    """Первая партия из текста PGN: теги, ходы SAN; комментарии, варианты, NAG пропускаются."""
    tags = {}
    body = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]") and not body:
            inner = s[1:-1]
            k, _, v = inner.partition(" ")
            tags[k] = v.strip().strip('"')
        elif s.startswith("%"):
            continue
        else:
            body.append(line)
    moves_text = "\n".join(body)
    out, depth, i = [], 0, 0
    while i < len(moves_text):
        ch = moves_text[i]
        if ch == "{":
            j = moves_text.find("}", i)
            i = len(moves_text) if j < 0 else j + 1
            continue
        if ch == ";":
            j = moves_text.find("\n", i)
            i = len(moves_text) if j < 0 else j + 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            out.append(ch)
        i += 1
    pos = from_fen(tags["FEN"]) if "FEN" in tags else start()
    game = Game(pos, tags={k: v for k, v in tags.items() if k not in ("FEN", "SetUp", "Result")})
    for tok in "".join(out).split():
        if tok in ("1-0", "0-1", "1/2-1/2", "*"):
            break
        if tok.startswith("$"):
            continue
        tok = tok.split(".")[-1]
        if not tok:
            continue
        game.push_san(tok)
    return game
