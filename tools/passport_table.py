"""Таблицы для README из паспортов моделей - чтобы числа в README были ровно числами паспорта.

    python tools/passport_table.py          # markdown на русском
    python tools/passport_table.py en
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.ai import games, models  # noqa: E402

NAMES = {
    "ru": {"vs_random": "случайный", "vs_greedy": "жадный", "vs_material2": "материал, гл. 2",
           "vs_material3": "материал, гл. 3", "vs_material4": "материал, гл. 4", "vs_material6": "материал, гл. 6",
           "level": "Уровень", "games": "Партий обучения", "depth": "Глубина",
           "novice": "новичок", "medium": "средний", "strong": "сильный",
           "checkers": "Шашки", "chess": "Шахматы"},
    "en": {"vs_random": "random", "vs_greedy": "greedy", "vs_material2": "material, d2",
           "vs_material3": "material, d3", "vs_material4": "material, d4", "vs_material6": "material, d6",
           "level": "Level", "games": "Training games", "depth": "Depth",
           "novice": "novice", "medium": "medium", "strong": "strong",
           "checkers": "Checkers", "chess": "Chess"},
}


def num(n, lang):
    return f"{n:,}".replace(",", " " if lang == "ru" else ",")


def table(kind, lang="ru"):
    t = NAMES[lang]
    pp = models.load_passport(kind)
    checks = [name for name, _ in games.CHECKS[kind]]
    head = [t["level"], t["games"], t["depth"]] + [t[c] for c in checks]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for lv in pp["levels"]:
        cells = [t[lv["key"]], num(lv["games"], lang), str(lv["depth"])]
        for c in checks:
            r = lv["checks"].get(c)
            cells.append(f"{r['wins']} / {r['draws']} / {r['losses']}" if r else "-")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def summary(kind, lang="ru"):
    pp = models.load_passport(kind)
    n = pp["network"]
    hours = pp["train_seconds"] / 3600
    if lang == "ru":
        return (f"{NAMES[lang][kind]}: сеть {n['planes']} → {n['channels']} × {n['conv_layers']} свёрток 3x3 → "
                f"{n['head']} → 1, {num(n['parameters'], lang)} весов; {num(pp['games'], lang)} партий самоигры за "
                f"{hours:.1f} ч".replace(".", ",") + f" на {pp['threads']} процессах.")
    return (f"{NAMES[lang][kind]}: network {n['planes']} → {n['channels']} × {n['conv_layers']} 3x3 convolutions → "
            f"{n['head']} → 1, {num(n['parameters'], lang)} weights; {num(pp['games'], lang)} self-play games in "
            f"{hours:.1f} h on {pp['threads']} processes.")


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "ru"
    for kind in games.GAMES:
        if models.has_model(kind):
            print(summary(kind, lang))
            print()
            print(table(kind, lang))
            print()
