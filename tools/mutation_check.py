"""Мутационная проверка: по одной ломаем правило в коде и убеждаемся, что тесты падают.

    python tools/mutation_check.py checkers
    python tools/mutation_check.py chess
    python tools/mutation_check.py search

Каждая мутация - замена строки в файле. Файл возвращается на место в любом случае (finally),
даже если прогон прерван. Мутация, которую тесты не заметили, печатается как ВЫЖИЛА и
даёт код возврата 1.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SETS = {
    "checkers": ("game/core/checkers.py", "tests/test_checkers.py", [
        ("простая не бьёт назад", "    for d in range(4):\n        ray = RAYS[cur][d]\n        if len(ray) < 2:",
         "    for d in FORWARD[side]:\n        ray = RAYS[cur][d]\n        if len(ray) < 2:"),
        ("взятие не обязательно", "    return caps if caps else quiet_moves(pos)", "    return caps + quiet_moves(pos)"),
        ("турецкий удар выключен", "        if board[over] * side > 0 or over in captured:",
         "        if board[over] * side > 0:"),
        ("дамка встаёт куда угодно, хотя бой продолжается", "        if cont:\n", "        if False:\n"),
        ("простая на последнем ряду посреди взятия не становится дамкой",
         "            if land in LAST_ROW[side]:", "            if False:"),
        ("простая ходит назад", "            for d in fwd:", "            for d in range(4):"),
        ("повторение - четыре раза", "        if self.counts.get(pos.key, 0) >= 3:", "        if self.counts.get(pos.key, 0) >= 4:"),
        ("ничья дамками - 16 ходов", "QUIET_LIMIT = 30 ", "QUIET_LIMIT = 32 "),
        ("дамка ходит на одно поле", "                    out.append(((s, t), ()))",
         "                    out.append(((s, t), ()))\n                    break"),
        ("простая прыгает через побитую", "        if p * side < 0 and over not in captured and",
         "        if p * side < 0 and"),
        ("начальное поле не освобождается", "(board[land] == 0 or land == origin)", "(board[land] == 0)"),
        ("превращение только на последнем поле пути",
         "    if man and any(s in LAST_ROW[side] for s in path[1:]):", "    if man and path[-1] in LAST_ROW[side]:"),
        ("дамка бьёт только вплотную", "        while i < n and (board[ray[i]] == 0 or ray[i] == origin):\n            i += 1\n        if i >= n:",
         "        if i >= n or board[ray[i]] == 0:"),
        ("сброс счётчика дамок забыт", "    quiet = 0 if (man or caps) else pos.quiet + 1", "    quiet = pos.quiet + 1"),
    ]),
}


def run(name, pytest_args=("-x", "-q", "-m", "not slow", "-p", "no:cacheprovider")):
    target, tests, mutations = SETS[name]
    path = ROOT / target
    original = path.read_text(encoding="utf-8")
    survived = []
    try:
        for title, old, new in mutations:
            if original.count(old) != 1:
                print(f"?  {title}: строка не найдена ровно один раз")
                survived.append(title)
                continue
            path.write_text(original.replace(old, new), encoding="utf-8", newline="\n")
            r = subprocess.run([sys.executable, "-m", "pytest", tests, *pytest_args], cwd=ROOT,
                               capture_output=True, text=True, timeout=1800)
            caught = r.returncode != 0
            print(f"{'поймана' if caught else 'ВЫЖИЛА '}  {title}")
            if not caught:
                survived.append(title)
    finally:
        path.write_text(original, encoding="utf-8", newline="\n")
    print(f"итог: {len(mutations) - len(survived)} из {len(mutations)} пойманы")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "checkers"))
