"""Правила русских шашек: ручная позиция на каждое правило spec §4, сверка со второй
медленной реализацией (tests/checkers_slow.py) по perft и на случайных позициях."""
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import checkers_slow as slow
from game.core import checkers as ck


def texts(pos):
    return sorted(ck.move_text(m) for m in ck.legal_moves(pos))


# --- ручные позиции, по правилу на тест ---


def test_start_position():
    pos = ck.start()
    assert sum(1 for p in pos.board if p == 1) == 12 and sum(1 for p in pos.board if p == -1) == 12
    assert pos.turn == ck.WHITE
    assert texts(pos) == ["a3-b4", "c3-b4", "c3-d4", "e3-d4", "e3-f4", "g3-f4", "g3-h4"]


def test_a1_is_a_dark_square_with_a_white_man():
    assert ck.start().board[ck.parse_square("a1")] == 1
    with pytest.raises(ValueError):
        ck.parse_square("b1")


def test_man_moves_only_forward():
    assert texts(ck.from_squares(white=["c3"], black=["h8"])) == ["c3-b4", "c3-d4"]
    assert texts(ck.from_squares(white=["a1"], black=["d6"], turn=ck.BLACK)) == ["d6-c5", "d6-e5"]


def test_man_captures_backward():
    assert texts(ck.from_squares(white=["d4"], black=["c3"])) == ["d4:b2"]


def test_capture_is_mandatory():
    # у белых есть тихий ход a1-b2, но взятие c3:e5 обязательно
    assert texts(ck.from_squares(white=["c3", "a1"], black=["d4"])) == ["c3:e5"]


def test_any_capture_may_be_chosen_not_only_the_longest():
    pos = ck.from_squares(white=["c3"], black=["b4", "d4", "f6"])
    assert texts(pos) == ["c3:a5", "c3:e5:g7"]


def test_started_chain_must_be_finished():
    pos = ck.from_squares(white=["c3"], black=["d4", "f6"])
    assert texts(pos) == ["c3:e5:g7"]          # остановиться на e5 нельзя


def test_turkish_strike_captured_piece_stays_until_the_end_of_the_move():
    # Дамка a7 бьёт c5 и обязана встать на e3 (оттуда бой идёт дальше). С e3 - d2 или f4.
    # Побив d2 и встав на c1, она упирается в ещё не снятую d2: f4 через неё не побить.
    pos = ck.from_squares(white_kings=["a7"], black=["d2", "f4", "c5"])
    assert texts(pos) == ["a7:e3:c1", "a7:e3:g5", "a7:e3:h6"]


def test_the_same_piece_is_never_jumped_twice():
    # простая обходит ромб и возвращается на d2; прыгнуть через e3 второй раз нельзя
    pos = ck.from_squares(white=["d2"], black=["e3", "e5", "c5", "c3"])
    moves = ck.legal_moves(pos)
    assert len(moves) == 1
    assert ck.move_text(moves[0]) in ("d2:f4:d6:b4:d2", "d2:b4:d6:f4:d2")
    assert len(moves[0][1]) == 4
    after = ck.play(pos, moves[0])
    assert sum(1 for p in after.board if p < 0) == 0


def test_king_moves_any_distance():
    assert texts(ck.from_squares(white_kings=["a1"], black=["h6"])) == \
        ["a1-b2", "a1-c3", "a1-d4", "a1-e5", "a1-f6", "a1-g7", "a1-h8"]


def test_king_captures_from_afar_and_lands_on_any_free_square_behind():
    pos = ck.from_squares(white_kings=["a1"], black=["c3"])
    assert texts(pos) == ["a1:d4", "a1:e5", "a1:f6", "a1:g7", "a1:h8"]


def test_king_must_land_where_the_capture_goes_on():
    # из всех полей за c3 бой продолжается только с e5 (там g3, за ней h2)
    pos = ck.from_squares(white_kings=["a1"], black=["c3", "g3"])
    assert texts(pos) == ["a1:e5:h2"]


def test_man_promoted_during_capture_goes_on_as_a_king():
    # b6 бьёт c7, становится дамкой на d8 и дальше бьёт f6 через пустое e7 - простая так не может
    pos = ck.from_squares(white=["b6"], black=["c7", "f6"])
    assert texts(pos) == ["b6:d8:g5", "b6:d8:h4"]
    after = ck.play(pos, ck.parse_move(pos, "b6:d8:h4"))
    assert after.board[ck.parse_square("h4")] == ck.KING


def test_promotion_by_a_quiet_move():
    pos = ck.from_squares(white=["c7"], black=["a1"])
    assert texts(pos) == ["c7-b8", "c7-d8"]
    assert ck.play(pos, ck.parse_move(pos, "c7-d8")).board[ck.parse_square("d8")] == ck.KING
    black = ck.from_squares(white=["h8"], black=["b2"], turn=ck.BLACK)
    assert ck.play(black, ck.parse_move(black, "b2-a1")).board[0] == -ck.KING


def test_no_moves_loses():
    game = ck.Game(ck.from_squares(white=["a1"], black=["b2", "c3"]))
    assert game.result() == (-1, "no_moves")


def test_no_pieces_loses():
    game = ck.Game(ck.from_squares(black=["b2"]))
    assert game.result() == (-1, "no_pieces")
    game = ck.Game(ck.from_squares(white=["b2"], turn=ck.BLACK))
    assert game.result() == (1, "no_pieces")


def test_threefold_repetition_is_a_draw():
    game = ck.Game(ck.from_squares(white_kings=["c1"], black_kings=["f8"]))
    for _ in range(2):
        for t in ("c1-d2", "f8-e7", "d2-c1", "e7-f8"):
            assert game.result() is None
            game.push(ck.parse_move(game.pos, t))
    assert game.result() == (0, "repetition")


def test_fifteen_moves_of_kings_only_is_a_draw():
    game = ck.Game(ck.from_squares(white_kings=["a1"], black_kings=["h8"], white=["a3"], quiet=29))
    game.push(ck.parse_move(game.pos, "a1-b2"))
    assert game.pos.quiet == 30 and game.result() == (0, "kings_only")


def test_man_move_or_capture_resets_the_kings_only_counter():
    pos = ck.from_squares(white_kings=["a1"], black_kings=["h8"], white=["a3"], quiet=20)
    assert ck.play(pos, ck.parse_move(pos, "a3-b4")).quiet == 0
    assert ck.play(pos, ck.parse_move(pos, "a1-b2")).quiet == 21
    cap = ck.from_squares(white_kings=["a1"], black=["c3"], quiet=20)
    assert ck.play(cap, ck.parse_move(cap, "a1:d4")).quiet == 0


def test_undo_restores_position_and_repetition_counts():
    game = ck.Game()
    first = game.pos
    game.push(game.legal()[0])
    game.pop()
    assert game.pos == first and game.counts[first.key] == 1 and game.pop() is None


def test_text_round_trip_and_zobrist_key():
    pos = ck.from_squares(white=["c3", "e1"], white_kings=["h8"], black=["d6"], black_kings=["a1"], turn=ck.BLACK)
    back = ck.from_text(ck.to_text(pos))
    assert back == pos and back.key == pos.key
    # ключ после хода - тот же, что посчитанный с нуля
    for m in ck.legal_moves(pos):
        nxt = ck.play(pos, m)
        assert nxt.key == ck.compute_key(nxt.board, nxt.turn)


def test_parse_move_refuses_wrong_moves():
    pos = ck.start()
    with pytest.raises(ValueError):
        ck.parse_move(pos, "c3-c4")
    with pytest.raises(ValueError):
        ck.parse_move(pos, "a3-a5")


# --- сверка с медленной реализацией ---


def canon(moves):
    """Ходы с одним началом, концом и набором побитых дают одну позицию - сравнивать их так."""
    return sorted((m[0][0], m[0][-1], tuple(sorted(m[1]))) for m in moves)


# Совпадают с английскими шашками до глубины 4; дальше русские правила (взятие простой
# назад) дают больше ходов. Числа - общий ответ двух независимых реализаций.
PERFT_START = {1: 7, 2: 49, 3: 302, 4: 1469, 5: 7482, 6: 37986}


@pytest.mark.parametrize("depth", sorted(PERFT_START))
def test_perft_start_matches_the_slow_implementation(depth):
    pos = ck.start()
    fast = ck.perft(pos, depth)
    assert fast == slow.perft(pos.board, pos.turn, depth)
    assert fast == PERFT_START[depth]


@pytest.mark.slow
def test_perft_start_depth_8_matches_the_slow_implementation():
    pos = ck.start()
    for depth in (7, 8):
        assert ck.perft(pos, depth) == slow.perft(pos.board, pos.turn, depth)


def random_game_positions(seed, plies=200):
    rng = random.Random(seed)
    pos = ck.start()
    out = [pos]
    for _ in range(plies):
        moves = ck.legal_moves(pos)
        if not moves:
            break
        pos = ck.play(pos, rng.choice(moves))
        out.append(pos)
    return out


@settings(max_examples=150, deadline=None)
@given(st.integers(0, 10 ** 9))
def test_random_games_both_implementations_agree(seed):
    for pos in random_game_positions(seed):
        assert canon(ck.legal_moves(pos)) == canon(slow.legal_moves(pos.board, pos.turn)), ck.to_text(pos)
        for m in ck.legal_moves(pos):
            assert ck.play(pos, m).board == slow.play(pos.board, pos.turn, m)


@settings(max_examples=400, deadline=None)
@given(st.lists(st.sampled_from([0, 0, 0, 1, -1, 2, -2]), min_size=32, max_size=32), st.sampled_from([1, -1]))
def test_random_boards_with_kings_both_implementations_agree(cells, turn):
    board = list(cells)
    for s in range(28, 32):          # простых на своём последнем ряду не бывает
        if board[s] == 1:
            board[s] = 2
    for s in range(4):
        if board[s] == -1:
            board[s] = -2
    pos = ck.Position(board, turn)
    assert canon(ck.legal_moves(pos)) == canon(slow.legal_moves(pos.board, pos.turn)), ck.to_text(pos)
