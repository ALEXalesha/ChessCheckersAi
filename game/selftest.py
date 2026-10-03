"""Самопроверка без экрана: python main.py --selftest итог.txt.

Нужна прежде всего собранному exe: он без консоли, поэтому итог пишется в файл. Окно
создаётся offscreen, данные игрока - во временной папке, статистику игрока она не трогает.
Проверяется: правила (perft), модели и паспорта, окно - сеть отвечает на ходы бота.
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
        home = tempfile.mkdtemp(prefix="chesscheckersai-selftest-")
        os.environ["CHESSCHECKERSAI_HOME"] = home
        import numpy as np
        from PySide6.QtWidgets import QApplication

        import aikit
        from aikit.host import make_window
        from game import APP_NAME, GAME_INFO, create_widget
        from game.ai import games, models
        from game.core import checkers, chess
        from game.version import VERSION

        lines.append(f"ChessCheckersAi {VERSION} самопроверка (aikit {aikit.__version__})")
        lines.append(f"собранная версия: {'да' if aikit.frozen() else 'нет'}")
        started = time.time()
        n = checkers.perft(checkers.start(), 6)
        lines.append(f"шашки: perft 6 = {n}, {time.time() - started:.2f} с")
        if n != 37986:
            raise RuntimeError("perft шашек не сошёлся")
        started = time.time()
        n = chess.perft(chess.from_fen("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"), 3)
        lines.append(f"шахматы: perft 3 Kiwipete = {n}, {time.time() - started:.2f} с")
        if n != 97862:
            raise RuntimeError("perft шахмат не сошёлся")
        for kind in games.GAMES:
            if models.has_model(kind):
                pp = models.load_passport(kind)
                lines.append(f"модель {kind}: {pp['games']} партий обучения, {pp['network']['parameters']} весов")
            else:
                lines.append(f"модель {kind}: нет (играет оценка по материалу)")

        app = QApplication.instance() or QApplication([])
        window, ctx = make_window(GAME_INFO, create_widget, APP_NAME, root=home)
        window.show()
        g = window.game
        g.change("mode", "net")
        g.change("color", "white")
        g.change("level", "novice")
        rng = np.random.default_rng(7)
        for kind, plies in (("checkers", 12), ("chess", 8)):
            g.change("game", kind)
            g.start_game()
            bot = games.make_player(kind, {"kind": "random"}, rng)
            t0 = time.time()
            while len(g.session.game.moves) < plies and g.session.result() is None:
                if g.session.human_turn():
                    g.on_move_chosen(bot.choose(g.session.game))
                end = time.time() + 30
                while g.session.net_turn() and time.time() < end:
                    app.processEvents()
                    time.sleep(0.005)
                if g.session.net_turn():
                    raise RuntimeError("сеть не ответила за 30 с")
            image = window.grab().toImage()
            if image.isNull() or image.width() < 300:
                raise RuntimeError("окно не нарисовалось")
            lines.append(f"{kind}: {len(g.session.game.moves)} полуходов против случайного бота, "
                         f"статус «{g.play.status.text()}», кадр {image.width()}x{image.height()}, "
                         f"{time.time() - t0:.2f} с")
        t0 = time.time()
        window.close()
        app.processEvents()
        lines.append(f"окно закрыто за {time.time() - t0:.2f} с")
        lines.append("ИТОГ: работает")
    except Exception:  # noqa: BLE001 - любая ошибка должна попасть в файл
        lines.append("ИТОГ: ошибка")
        lines.append(traceback.format_exc())
        code = 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return code
