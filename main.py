"""Шашки и шахматы с нейросетью.

    python main.py                         # игра
    python main.py --offscreen             # без экрана (проверки)
    python main.py --selftest итог.txt     # самопроверка без экрана, итог в файл
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Шашки и шахматы с нейросетью")
    ap.add_argument("--selftest", metavar="ФАЙЛ", nargs="?", const="selftest.txt",
                    help="без окна сыграть сетью против бота и записать итог в файл")
    ap.add_argument("--offscreen", action="store_true", help="без экрана")
    args = ap.parse_args(argv)
    if args.selftest:
        from game.selftest import selftest
        return selftest(args.selftest)
    if args.offscreen:
        from aikit import offscreen
        offscreen.setup(force=True)
    import aikit
    from game import APP_NAME, GAME_INFO, create_widget
    return aikit.run_standalone(GAME_INFO, create_widget, APP_NAME)


if __name__ == "__main__":
    sys.exit(main())
