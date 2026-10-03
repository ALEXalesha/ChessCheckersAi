"""Готовые модели: в одном файле models/<игра>.npz три снимка обучения - новичок, средний,
сильный (spec §3: уровни - снимки одного обучения). Рядом паспорт models/<игра>.json."""
import json
import os
from functools import lru_cache

import numpy as np

from aikit.nn import io
from game.ai.net import ValueNet

LEVELS = ("novice", "medium", "strong")
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")


def model_path(game, folder=None):
    return os.path.join(folder or models_dir(), f"{game}.npz")


def passport_path(game, folder=None):
    return os.path.join(folder or models_dir(), f"{game}.json")


def models_dir():
    """game/models рядом с кодом; в собранном exe - внутри _MEIPASS (та же раскладка)."""
    return MODELS_DIR


def save_levels(path, nets):
    """nets - {уровень: ValueNet} с одной архитектурой."""
    arrays = {}
    config = None
    for level, net in nets.items():
        config = net.config
        for name, p in net.arrays().items():
            arrays[f"{level}.{name}"] = p
    arrays["meta"] = np.array(json.dumps({"config": config, "levels": list(nets)}))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    io.save(path, arrays)


def load_level(path, level):
    arrays = io.load(path)
    meta = json.loads(str(arrays["meta"]))
    if level not in meta["levels"]:
        raise KeyError(f"в {os.path.basename(path)} нет уровня {level}")
    net = ValueNet(**meta["config"])
    net.set_arrays({k.split(".", 1)[1]: v for k, v in arrays.items() if k.startswith(level + ".")})
    return net


@lru_cache(maxsize=None)
def cached_level(path, level):
    return load_level(path, level)


def load_passport(game, folder=None):
    with open(passport_path(game, folder), encoding="utf-8") as f:
        return json.load(f)


def has_model(game, folder=None):
    return os.path.exists(model_path(game, folder))
