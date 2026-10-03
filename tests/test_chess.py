"""Правила шахмат: perft на позициях с известными числами (Chess Programming Wiki), ручные
позиции на рокировку, взятие на проходе, превращение, мат, пат, ничьи; SAN, FEN, PGN."""
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from game.core import chess as c

KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
POS3 = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
POS4 = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"
POS5 = "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8"
POS6 = "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10"

PERFT = {
    c.START_FEN: [20, 400, 8902, 197281, 4865609],
    KIWIPETE: [48, 2039, 97862, 4085603],
    POS3: [14, 191, 2812, 43238, 674624],
    POS4: [6, 264, 9467, 422333],
    POS5: [44, 1486, 62379, 2103487],
    POS6: [46, 2079, 89890, 3894594],
}


@pytest.mark.parametrize("fen", list(PERFT))
def test_perft_shallow(fen):
    pos = c.from_fen(fen)
    want = PERFT[fen][:3]
    assert [c.perft(pos, d) for d in range(1, len(want) + 1)] == want


@pytest.mark.slow
@pytest.mark.parametrize("fen", list(PERFT))
def test_perft_deep(fen):
    """Начальная позиция до глубины 5 (4 865 609), Kiwipete до 4, позиции 3-6 CPW."""
    pos = c.from_fen(fen)
    assert c.perft(pos, len(PERFT[fen])) == PERFT[fen][-1]


def sans(fen):
    pos = c.from_fen(fen)
    return sorted(c.san(pos, m) for m in c.legal_moves(pos))


# --- рокировка ---


def test_castling_both_sides():
    s = sans("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert "O-O" in s and "O-O-O" in s
    pos = c.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    after = c.play(pos, c.parse_san(pos, "O-O"))
    assert after.board[c.parse_square("g1")] == c.KING and after.board[c.parse_square("f1")] == c.ROOK
    assert after.castling == c.BK | c.BQ


def test_no_castling_out_of_check_or_through_attacked_squares():
    assert "O-O" not in sans("4r1k1/8/8/8/8/8/8/4K2R w K - 0 1")       # шах
    assert "O-O" not in sans("5rk1/8/8/8/8/8/8/4K2R w K - 0 1")        # f1 под боем
    assert "O-O" not in sans("6rk/8/8/8/8/8/8/4K2R w K - 0 1")         # g1 под боем
    # b1 под боем - длинной рокировке не мешает: король через b1 не идёт
    assert "O-O-O" in sans("1r5k/8/8/8/8/8/8/R3K3 w Q - 0 1")
    assert "O-O-O" not in sans("2r4k/8/8/8/8/8/8/R3K3 w Q - 0 1")      # c1 под боем
    assert "O-O-O" not in sans("7k/8/8/8/8/8/8/RN2K3 w Q - 0 1")       # b1 занято


def test_castling_rights_are_lost_when_king_or_rook_moves_or_rook_is_taken():
    pos = c.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert c.play(pos, c.parse_san(pos, "Kf1")).castling == c.BK | c.BQ
    assert c.play(pos, c.parse_san(pos, "Rb1")).castling == c.WK | c.BK | c.BQ
    assert c.play(pos, c.parse_san(pos, "Rh2")).castling == c.WQ | c.BK | c.BQ
    assert c.play(pos, c.parse_san(pos, "Rxa8+")).castling == c.WK | c.BK


# --- взятие на проходе ---


def test_en_passant_right_after_the_double_step_only():
    g = c.Game(c.from_fen("4k3/3p4/8/4P3/8/8/8/4K3 b - - 0 1"))
    g.push_san("d5")
    assert g.pos.ep == c.parse_square("d6")
    after = c.play(g.pos, c.parse_san(g.pos, "exd6"))
    assert after.board[c.parse_square("d5")] == 0 and after.board[c.parse_square("d6")] == c.PAWN
    g.push_san("Kd1")
    g.push_san("Ke7")
    assert "exd6" not in [c.san(g.pos, x) for x in g.legal()]


def test_en_passant_that_exposes_the_king_is_illegal():
    # белый король и чёрная ладья на 5-м ряду: взятие убрало бы обе пешки с линии
    pos = c.from_fen("8/8/8/KPp4r/8/8/8/7k w - c6 0 1")
    assert "bxc6" not in sans(c.to_fen(pos))


def test_ep_square_kept_only_when_someone_can_take():
    pos = c.play(c.start(), c.parse_san(c.start(), "e4"))
    assert pos.ep is None and c.to_fen(pos).split()[3] == "-"


# --- превращение, мат, пат ---


def test_promotion_to_any_piece():
    s = sans("8/P6k/8/8/8/8/8/K7 w - - 0 1")
    for p in ("Q", "R", "B", "N"):
        assert f"a8={p}" in s or f"a8={p}+" in s
    pos = c.from_fen("8/P6k/8/8/8/8/8/K7 w - - 0 1")
    assert c.play(pos, c.parse_san(pos, "a8=N")).board[c.parse_square("a8")] == c.KNIGHT


def test_checkmate_and_stalemate():
    g = c.Game()
    for s in ("f3", "e5", "g4", "Qh4#"):
        g.push_san(s)
    assert g.result() == (-1, "checkmate") and g.sans[-1] == "Qh4#"
    assert c.Game(c.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")).result() == (0, "stalemate")


# --- ничьи ---


def test_fifty_move_rule():
    g = c.Game(c.from_fen("7k/8/8/8/8/8/8/R6K w - - 99 80"))
    assert g.result() is None
    g.push_san("Ra2")
    assert g.result() == (0, "fifty")
    # взятие или ход пешкой обнуляет счётчик
    pos = c.from_fen("7k/8/8/8/8/8/P7/R6K w - - 99 80")
    assert c.play(pos, c.parse_san(pos, "a3")).halfmove == 0


def test_threefold_repetition():
    g = c.Game()
    for _ in range(2):
        for s in ("Nf3", "Nf6", "Ng1", "Ng8"):
            assert g.result() is None
            g.push_san(s)
    assert g.result() == (0, "repetition")


@pytest.mark.parametrize("fen, draw", [
    ("7k/8/8/8/8/8/8/K7 w - - 0 1", True),
    ("7k/8/8/8/8/8/8/KN6 w - - 0 1", True),
    ("7k/8/8/8/8/8/8/KB6 w - - 0 1", True),
    ("6bk/8/8/8/8/8/8/KB6 w - - 0 1", True),       # g8 и b1 - оба светлые поля
    ("7k/6b1/8/8/8/8/8/KB6 w - - 0 1", False),     # g7 тёмное, b1 светлое
    ("7k/8/8/8/8/8/8/KNN5 w - - 0 1", False),
    ("7k/8/8/8/8/8/P7/K7 w - - 0 1", False),
    ("7k/8/8/8/8/8/8/KR6 w - - 0 1", False),
])
def test_insufficient_material(fen, draw):
    assert c.insufficient_material(c.from_fen(fen)) is draw


# --- SAN, FEN, PGN ---


def test_san_disambiguation_and_checks():
    s = sans("4k3/8/8/8/8/8/3K4/R6R w - - 0 1")
    assert "Rab1" in s and "Rhb1" in s
    s = sans("4k3/8/8/R7/8/8/8/R3K3 w - - 0 1")
    assert "R1a3" in s and "R5a3" in s
    s = sans("k7/8/8/8/8/1Q6/8/1Q1Q3K w - - 0 1")          # три ферзя бьют d3
    assert {"Qb1d3", "Qdd3", "Q3d3"} <= set(s)
    assert "Ra8+" in sans("4k3/8/8/8/8/8/8/R3K3 w - - 0 1") or "Ra8#" in sans("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")


def test_fen_round_trip_for_cpw_positions():
    for fen in PERFT:
        assert c.to_fen(c.from_fen(fen)) == fen


def test_pgn_round_trip():
    g = c.Game()
    for s in ("e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7"):
        g.push_san(s)
    text = c.to_pgn(g, {"White": "Сеть", "Black": "Человек"})
    assert '[White "Сеть"]' in text and "1. e4 e5 2. Nf3" in text and text.rstrip().endswith("*")
    back = c.from_pgn(text)
    assert back.sans == g.sans and back.pos == g.pos


def test_pgn_with_comments_variations_and_setup():
    text = ('[Event "x"]\n[SetUp "1"]\n[FEN "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"]\n\n'
            '1. O-O {рокировка} (1. O-O-O O-O) 1... O-O-O $1 2. Rfe1 ; комментарий\n Rhe8 1/2-1/2\n')
    g = c.from_pgn(text)
    assert g.sans == ["O-O", "O-O-O", "Rfe1", "Rhe8"]
    out = c.to_pgn(g)
    assert '[FEN "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"]' in out


def test_bad_san_is_an_error():
    with pytest.raises(ValueError):
        c.parse_san(c.start(), "e5")
    with pytest.raises(ValueError):
        c.from_fen("8/8/8 w - - 0 1")


def random_positions(seed, plies=120):
    rng = random.Random(seed)
    g = c.Game()
    out = [g.pos]
    for _ in range(plies):
        if g.result() is not None:
            break
        g.push(rng.choice(g.legal()))
        out.append(g.pos)
    return out


@settings(max_examples=12, deadline=None)
@given(st.integers(0, 10 ** 9))
def test_random_games_keep_invariants(seed):
    for pos in random_positions(seed, plies=80):
        assert pos.key == c.compute_key(pos)                       # ключ после хода = с нуля
        back = c.from_fen(c.to_fen(pos))
        assert back == pos and back.key == pos.key
        assert pos.kings[c.WHITE] == pos.board.index(c.KING) and pos.kings[c.BLACK] == pos.board.index(-c.KING)
        assert not c.in_check(pos, -pos.turn)                      # свой король после хода не под боем
        for m in c.legal_moves(pos):
            assert c.parse_san(pos, c.san(pos, m)) == m
