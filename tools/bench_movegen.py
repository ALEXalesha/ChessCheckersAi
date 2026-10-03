"""Скорость генератора ходов (для README): perft с подсчётом листьев.

    python tools/bench_movegen.py

Шашки - perft 8 от начальной позиции, шахматы - perft 4 от начальной и Kiwipete 3.
Печатает листья в секунду и позиции (узлы, где строился список ходов) в секунду.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.core import checkers as ck  # noqa: E402
from game.core import chess as ch  # noqa: E402


def count_nodes(perft_fn, pos, depth):
    """Позиции, в которых строился список ходов (внутренние узлы perft с последним уровнем
    «пачкой»): perft(d-1) + perft(d-2) + ... + 1."""
    return sum(perft_fn(pos, d) for d in range(depth))


def bench(name, perft_fn, pos, depth):
    t = time.perf_counter()
    leaves = perft_fn(pos, depth)
    sec = time.perf_counter() - t
    nodes = count_nodes(perft_fn, pos, depth)
    print(f"{name}: perft {depth} = {leaves:,} за {sec:.2f} с - {leaves / sec:,.0f} листьев/с, "
          f"{nodes / sec:,.0f} позиций/с".replace(",", " "))


if __name__ == "__main__":
    bench("шашки, начало", ck.perft, ck.start(), 8)
    bench("шахматы, начало", ch.perft, ch.start(), 4)
    bench("шахматы, Kiwipete", ch.perft,
          ch.from_fen("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"), 3)
