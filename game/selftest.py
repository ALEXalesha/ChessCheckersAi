"""Самопроверка без экрана: python main.py --selftest итог.txt.

Нужна прежде всего собранному exe: он без консоли, поэтому итог пишется в файл. Данные
игрока - во временной папке, статистику игрока она не трогает.
"""
import os
import tempfile
import time
import traceback


def selftest(out_path):
    lines = []
    code = 0
    try:
        from aikit import offscreen
        offscreen.setup(force=True)
        os.environ["CHESSCHECKERSAI_HOME"] = tempfile.mkdtemp(prefix="chesscheckersai-selftest-")
        from game.core import checkers
        from game.version import VERSION
        lines.append(f"ChessCheckersAi {VERSION} самопроверка")
        started = time.time()
        n = checkers.perft(checkers.start(), 6)
        lines.append(f"шашки: perft 6 = {n}, {time.time() - started:.2f} с")
        if n != 37986:
            raise RuntimeError("perft шашек не сошёлся")
        from game.core import chess
        started = time.time()
        n = chess.perft(chess.from_fen("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"), 3)
        lines.append(f"шахматы: perft 3 Kiwipete = {n}, {time.time() - started:.2f} с")
        if n != 97862:
            raise RuntimeError("perft шахмат не сошёлся")
        lines.append("ИТОГ: работает")
    except Exception:  # noqa: BLE001 - любая ошибка должна попасть в файл
        lines.append("ИТОГ: ошибка")
        lines.append(traceback.format_exc())
        code = 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return code
