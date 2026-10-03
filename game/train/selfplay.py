"""Обучение сети самоигрой: с нуля, только по исходам партий. TD-Leaf(λ).

    python -m game.train --game checkers --threads 4
    python -m game.train --game checkers --recheck          # только проверки уровней

Сеть играет сама с собой: каждый ход - поиск альфа-бета на малую глубину, листья
оценивает та же сеть. С вероятностью ε ход случайный (ε падает по ходу обучения), первые
полуходы партии - случайные, чтобы партии не повторялись.

Цель TD-Leaf: обучается не позиция в корне, а лист главной линии поиска - та позиция, чью
оценку поиск на самом деле поднял в корень. Цель - λ-возврат по оценкам поиска на
следующих ходах и исходу партии:
    G_t = γ · ((1 - λ) · (-s_{t+1}) + λ · (-G_{t+1})),   в конце партии - исход,
минус - потому что следующий ход делает соперник. Если следующий ход был случайным, след
обрывается: G_t = γ · (-s_{t+1}).

Партии играют процессы-работники (их число - --threads, в каждом один поток BLAS), сеть
учится в главном процессе на буфере последних позиций (MSE, Adam), пока работники уже
играют следующую пачку со свежими весами. Журнал - в файл, снимок состояния - после
каждой пачки, прерванное обучение продолжается с места.
"""
import json
import os
import sys
import time
from functools import partial
from pathlib import Path

import numpy as np

from aikit import tournament, trainlog
from aikit.nn import losses
from aikit.nn.optim import Adam
from game.ai import games, models, net
from game.ai.search import MATE, Searcher

LEVEL_NAMES = {"novice": "новичок", "medium": "средний", "strong": "сильный"}

PRESETS = {
    "checkers": {
        "games": 40000, "snapshots": {"novice": 2000, "medium": 12000},
        "net": {"channels": 32, "conv_layers": 3, "head": 64},
        "depth": 2, "lam": 0.7, "gamma": 0.99, "eps_start": 0.15, "eps_end": 0.02,
        "opening": 2, "max_plies": 240, "lr": 1e-3, "lr_end": 2e-4, "batch": 256,
        "replay": 4.0, "buffer": 300_000, "games_per_task": 4, "eval_every": 2000, "eval_games": 40,
    },
    "chess": {
        "games": 20000, "snapshots": {"novice": 1000, "medium": 6000},
        # две свёртки, а не три, как у шашек: полуход самоигры 25 мс против 34 мс,
        # а время обучения шахмат ограничено (замер 03.10)
        "net": {"channels": 32, "conv_layers": 2, "head": 64},
        "depth": 1, "lam": 0.7, "gamma": 0.995, "eps_start": 0.15, "eps_end": 0.02,
        "opening": 4, "max_plies": 300, "lr": 1e-3, "lr_end": 2e-4, "batch": 256,
        "replay": 4.0, "buffer": 300_000, "games_per_task": 2, "eval_every": 1000, "eval_games": 40,
    },
}


def default_run_dir(game):
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "ChessCheckersAi", "runs", game)


# --- самоигра (в процессе-работнике) ---

_worker_model = {}


def _model_for(game, config, weights):
    key = (game, json.dumps(config, sort_keys=True))
    model = _worker_model.get(key)
    if model is None:
        model = net.ValueNet(games.planes(game), **config)
        _worker_model[key] = model
    model.set_arrays(weights)
    return model


def play_selfplay_game(game, model, rng, depth, eps, opening, max_plies, lam, gamma):
    """Одна партия сети с собой. Возвращает (листья (N, 8, 8, P) int8, цели (N,) float32,
    исход для белых или None при пределе длины, число полуходов)."""
    ad = games.adapter(game)
    enc = games.encoder(game)
    searcher = Searcher(ad, net.NetEval(model, enc))
    g = games.new_game(game)
    records = []
    plies = 0
    outcome = None
    while True:
        res = g.result()
        if res is not None:
            outcome = res[0]
            break
        if plies >= max_plies:
            break
        moves = g.legal()
        if plies < opening:
            g.push(moves[int(rng.integers(len(moves)))])
            plies += 1
            continue
        r = searcher.search(g.pos, depth=depth, history=[p.key for p in g.positions[:-1]])
        explored = rng.random() < eps
        move = moves[int(rng.integers(len(moves)))] if explored else r.move
        s = float(np.sign(r.score)) if abs(r.score) > MATE - 1 else float(np.clip(r.score, -1.0, 1.0))
        records.append((r.leaf, s, g.pos.turn, explored))
        g.push(move)
        plies += 1
    if not records:
        return np.zeros((0, 8, 8, games.planes(game)), np.int8), np.zeros(0, np.float32), outcome, plies
    targets = leaf_targets(records, outcome, lam, gamma)
    leaves = enc([rec[0] for rec in records])
    return leaves.astype(np.int8) if game == "checkers" else leaves, targets, outcome, plies


def leaf_targets(records, outcome, lam, gamma):
    """records - [(лист, оценка поиска s для ходившего, кто ходил, ход случайный)];
    outcome - исход для белых (1/0/-1) или None (предел длины: в конце берётся своя оценка).
    Возвращает цели для листьев с точки зрения сходившего в листе."""
    n = len(records)
    out = np.zeros(n, np.float32)
    g_next = None
    for t in range(n - 1, -1, -1):
        leaf, s, mover, _ = records[t]
        if t == n - 1:
            g = float(outcome * mover) if outcome is not None else s
        else:
            s_next = records[t + 1][1]
            if records[t + 1][3]:
                g = gamma * (-s_next)
            else:
                g = gamma * ((1 - lam) * (-s_next) + lam * (-g_next))
        g_next = g
        sign = 1.0 if -leaf.turn == mover else -1.0
        out[t] = sign * g
    return out


def selfplay_task(args):
    """Работа для процесса: несколько партий со своими зёрнами."""
    game, config, weights, seeds, eps, cfg = args
    model = _model_for(game, config, weights)
    xs, ys, info = [], [], {"white": 0, "black": 0, "draws": 0, "limit": 0, "plies": 0}
    for seed in seeds:
        rng = np.random.default_rng(seed)
        x, y, outcome, plies = play_selfplay_game(game, model, rng, cfg["depth"], eps, cfg["opening"],
                                                  cfg["max_plies"], cfg["lam"], cfg["gamma"])
        xs.append(x)
        ys.append(y)
        info["plies"] += plies
        if outcome is None:
            info["limit"] += 1
        else:
            info[{1: "white", -1: "black", 0: "draws"}[outcome]] += 1
    return np.concatenate(xs), np.concatenate(ys), info


def _init_worker():
    trainlog.limit_threads(1, force=True)


# --- проверки ---


def evaluate_level(game, model, level, checks, games_n, seed, processes=1, pool=None, indices=None):
    """Проверки уровня против ботов: {имя: итог турнира}."""
    depth = games.LEVEL_DEPTH[game][level]
    out = {}
    for name, opponent in checks:
        play = partial(games.play_one, game=game, subject={"kind": "net", "level": level, "depth": depth},
                       opponent=opponent, model=model)
        res = tournament.run(play, games_n, seed, indices=indices, processes=processes, pool=pool)
        out[name] = tournament.summary(res)
    return out


# --- обучение ---


class Trainer:
    def __init__(self, game, run_dir, out_dir, threads=4, seed=0, log=None, **overrides):
        self.game = game
        self.cfg = {**PRESETS[game], **overrides}
        self.run_dir = Path(run_dir)
        self.out_dir = Path(out_dir) if out_dir else None
        self.threads = threads
        self.seed = seed
        self.log = log or trainlog.TrainLog(self.run_dir / "train.log")
        self.snapshot = self.run_dir / "snapshot.npz"
        self.model = net.ValueNet(games.planes(game), rng=np.random.default_rng(seed), **self.cfg["net"])
        self.opt = Adam(self.model.params(), lr=self.cfg["lr"])
        planes = games.planes(game)
        dtype = np.int8 if game == "checkers" else np.float32
        self.buf_x = np.zeros((self.cfg["buffer"], 8, 8, planes), dtype)
        self.buf_y = np.zeros(self.cfg["buffer"], np.float32)
        self.filled = 0
        self.head = 0
        self.played = 0
        self.seconds = 0.0
        self.curve = []
        self.taken = {}
        self.rng = np.random.default_rng(seed + 7)
        self.loss = 0.0

    # снимок
    def save(self):
        arrays = {f"w.{k}": v for k, v in self.model.arrays().items()}
        for i, (m, v) in enumerate(zip(self.opt.m, self.opt.v)):
            arrays[f"m.{i}"] = m
            arrays[f"v.{i}"] = v
        for lv, (at, w) in self.taken.items():
            for k, v in w.items():
                arrays[f"level.{lv}.{k}"] = v
        arrays["buf_x"] = self.buf_x[:self.filled]
        arrays["buf_y"] = self.buf_y[:self.filled]
        meta = {"game": self.game, "played": self.played, "seconds": self.seconds, "curve": self.curve,
                "taken": {lv: at for lv, (at, _) in self.taken.items()}, "adam_t": self.opt.t,
                "head": self.head, "filled": self.filled, "cfg": self.cfg}
        trainlog.save_snapshot(self.snapshot, arrays, meta)

    def resume(self):
        snap = trainlog.load_snapshot(self.snapshot)
        if snap is None:
            return False
        arrays, meta = snap
        if meta.get("cfg", {}).get("net") != self.cfg["net"]:
            raise SystemExit("снимок от сети другого размера - удалите его или задайте ту же сеть")
        self.model.set_arrays({k[2:]: v for k, v in arrays.items() if k.startswith("w.")})
        for i in range(len(self.opt.m)):
            self.opt.m[i][...] = arrays[f"m.{i}"]
            self.opt.v[i][...] = arrays[f"v.{i}"]
        self.opt.t = meta["adam_t"]
        self.filled, self.head = meta["filled"], meta["head"]
        self.buf_x[:self.filled] = arrays["buf_x"]
        self.buf_y[:self.filled] = arrays["buf_y"]
        self.played, self.seconds, self.curve = meta["played"], meta["seconds"], meta["curve"]
        for lv, at in meta["taken"].items():
            w = {k[len(f"level.{lv}."):]: v for k, v in arrays.items() if k.startswith(f"level.{lv}.")}
            self.taken[lv] = (at, w)
        self.log(f"продолжаю со снимка: партий {self.played}, {self.seconds / 60:.1f} мин обучения")
        return True

    def eps(self):
        c = self.cfg
        frac = min(1.0, self.played / max(c["games"] * 0.8, 1))
        return c["eps_start"] + (c["eps_end"] - c["eps_start"]) * frac

    def lr(self):
        c = self.cfg
        frac = min(1.0, self.played / max(c["games"], 1))
        return c["lr"] * (c["lr_end"] / c["lr"]) ** frac

    def add(self, x, y):
        n = len(x)
        if n == 0:
            return
        pos = (self.head + np.arange(n)) % len(self.buf_y)
        self.buf_x[pos], self.buf_y[pos] = x, y
        self.head = int((self.head + n) % len(self.buf_y))
        self.filled = min(len(self.buf_y), self.filled + n)

    def learn(self, new_samples):
        c = self.cfg
        updates = max(1, int(round(new_samples * c["replay"] / c["batch"])))
        self.opt.lr = self.lr()
        losses_ = []
        for _ in range(updates):
            pick = self.rng.integers(0, self.filled, size=min(c["batch"], self.filled))
            x = self.buf_x[pick].astype(np.float32)
            pred = self.model.forward(x)
            loss, grad = losses.mse(pred, self.buf_y[pick][:, None])
            self.model.backward(grad)
            self.opt.step()
            losses_.append(loss)
        self.loss = float(np.mean(losses_))
        return updates

    def tasks(self, count):
        c = self.cfg
        weights = self.model.arrays()
        per = c["games_per_task"]
        out = []
        base = self.seed * 10_000_019 + self.played
        for k in range(0, count, per):
            seeds = [base + k + j for j in range(min(per, count - k))]
            out.append((self.game, c["net"], weights, seeds, self.eps(), c))
        return out

    def quick_eval(self, pool):
        """Короткая проверка для кривой обучения: против случайного и жадного."""
        model = self.model
        res = {}
        # в шашках жадный почти не отличается от случайного (взятие и так обязательно),
        # поэтому вторая проверка - альфа-бета по материалу на глубину 2
        for name, opp in (("vs_random", {"kind": "random"}), ("vs_material2", {"kind": "material", "depth": 2})):
            play = partial(games.play_one, game=self.game, subject={"kind": "net", "depth": 1}, opponent=opp,
                           model=model)
            r = tournament.summary(tournament.run(play, self.cfg["eval_games"], seed=self.played, pool=pool))
            res[name] = r["score"]
        return res

    def run(self, total=None, stop_after=None):
        """Учить до total партий (по умолчанию из пресета). stop_after - секунды: выйти
        раньше (снимок остаётся, можно продолжить)."""
        import multiprocessing as mp
        c = self.cfg
        total = total or c["games"]
        started = time.time()
        base_seconds = self.seconds
        round_games = self.threads * c["games_per_task"] * 2
        next_eval = (self.played // c["eval_every"] + 1) * c["eval_every"]
        self.log(f"обучение {self.game}: сеть {self.model.config}, весов {self.model.count()}, "
                 f"потоков {self.threads}, глубина {c['depth']}, цель {total} партий")
        with mp.get_context("spawn").Pool(self.threads, initializer=_init_worker) as pool:
            pending = pool.map_async(selftask_entry, self.tasks(min(round_games, total - self.played)))
            while True:
                results = pending.get()
                round_started = time.time()
                count = 0
                new = 0
                info = {"white": 0, "black": 0, "draws": 0, "limit": 0, "plies": 0}
                for x, y, inf in results:
                    self.add(x, y)
                    new += len(y)
                    for k in info:
                        info[k] += inf[k]
                    count += inf["white"] + inf["black"] + inf["draws"] + inf["limit"]
                self.played += count
                remaining = total - self.played
                stop = remaining <= 0 or (stop_after is not None and time.time() - started > stop_after)
                if not stop:
                    # работники играют следующую пачку, пока сеть учится на этой
                    pending = pool.map_async(selftask_entry, self.tasks(min(round_games, remaining)))
                self.learn(new)
                self.seconds = base_seconds + (time.time() - started)
                for lv, at in c["snapshots"].items():
                    if lv not in self.taken and self.played >= at:
                        self.taken[lv] = (self.played, self.model.arrays())
                        self.log(f"снят уровень «{LEVEL_NAMES[lv]}» на {self.played} партиях")
                rate = self.played / max(self.seconds, 1e-9)
                line = (f"партий {self.played:6d}  ε {self.eps():.3f}  lr {self.opt.lr:.5f}  потеря {self.loss:.4f}  "
                        f"белые/чёрные/ничьи/предел {info['white']}/{info['black']}/{info['draws']}/{info['limit']}  "
                        f"полуходов в партии {info['plies'] / max(count, 1):.0f}  "
                        f"{rate * 3600:.0f} партий/ч  обучение {time.time() - round_started:.1f} с")
                if self.played >= next_eval:
                    q = self.quick_eval(pool)
                    self.curve.append({"games": self.played, **q, "minutes": round(self.seconds / 60, 1)})
                    line += f"  проверка: случайный {q['vs_random']:.2f}, материал-2 {q['vs_material2']:.2f}"
                    next_eval += c["eval_every"]
                self.log(line)
                self.save()
                if stop:
                    break
        return self.played >= total

    def finish(self, eval_games=200, levels_out=True):
        """Уровни: снимки + конец обучения. Проверки против ботов, модели и паспорт в out_dir."""
        import multiprocessing as mp
        if "strong" not in self.taken:
            self.taken["strong"] = (self.played, self.model.arrays())
        nets = {}
        for lv in models.LEVELS:
            at, w = self.taken.get(lv, self.taken["strong"])
            m = net.ValueNet(games.planes(self.game), **self.cfg["net"])
            m.set_arrays(w)
            nets[lv] = m
        if levels_out and self.out_dir is not None:
            models.save_levels(models.model_path(self.game, self.out_dir), nets)
        passport = make_passport(self, nets)
        with mp.get_context("spawn").Pool(self.threads, initializer=_init_worker) as pool:
            for entry in passport["levels"]:
                t0 = time.time()
                entry["checks"] = evaluate_level(self.game, nets[entry["key"]], entry["key"],
                                                 games.CHECKS[self.game], eval_games, CHECK_SEED[self.game], pool=pool)
                entry["check_seconds"] = round(time.time() - t0, 1)
                self.log(f"{entry['name']}: " + ", ".join(
                    f"{k} {v['wins']}/{v['draws']}/{v['losses']}" for k, v in entry["checks"].items())
                    + f"  ({entry['check_seconds']:.0f} с)")
                write_passport(self.game, passport, self.out_dir)
        return passport


CHECK_SEED = {"checkers": 6001, "chess": 7001}


def selftask_entry(args):
    return selfplay_task(args)


def make_passport(trainer, nets):
    c = trainer.cfg
    net0 = nets["strong"]
    return {
        "game": trainer.game,
        "network": {**net0.config, "parameters": net0.count(),
                    "input": "плоскости 8x8 глазами сходившего", "output": "tanh, исход для сходившего"},
        "method": {"targets": "TD-Leaf(λ): лист главной линии поиска, λ-возврат по оценкам поиска и исходу",
                   "search_depth": c["depth"], "lambda": c["lam"], "gamma": c["gamma"],
                   "eps_start": c["eps_start"], "eps_end": c["eps_end"], "random_opening_plies": c["opening"],
                   "max_plies": c["max_plies"], "lr": c["lr"], "lr_end": c["lr_end"], "batch": c["batch"],
                   "replay": c["replay"], "buffer": c["buffer"], "seed": trainer.seed},
        "games": trainer.played,
        "train_seconds": round(trainer.seconds, 1),
        "threads": trainer.threads,
        "curve": trainer.curve,
        "checks_rules": {"games": None, "seed": CHECK_SEED[trainer.game],
                         "opening_random_plies": list(games.OPENING[trainer.game]),
                         "max_plies": games.MAX_PLIES[trainer.game],
                         "colors": "чётные партии сеть начинает белыми, нечётные - чёрными",
                         "per_game_seed": "numpy.random.default_rng([seed, номер партии])"},
        "levels": [{"key": lv, "name": LEVEL_NAMES[lv], "games": trainer.taken.get(lv, trainer.taken["strong"])[0],
                    "depth": games.LEVEL_DEPTH[trainer.game][lv], "checks": {}} for lv in models.LEVELS],
    }


def write_passport(game, passport, out_dir):
    if out_dir is None:
        return
    for lv in passport["levels"]:
        if lv["checks"]:
            passport["checks_rules"]["games"] = next(iter(lv["checks"].values()))["games"]
    path = models.passport_path(game, out_dir)
    Path(path).write_text(json.dumps(passport, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


def recheck(game, out_dir, threads=4, eval_games=200, log=print, levels=None):
    """Заново проверить сохранённые уровни и переписать итоги в паспорте - без обучения."""
    import multiprocessing as mp
    passport = models.load_passport(game, out_dir)
    with mp.get_context("spawn").Pool(threads, initializer=_init_worker) as pool:
        for entry in passport["levels"]:
            if levels and entry["key"] not in levels:
                continue
            model = models.load_level(models.model_path(game, out_dir), entry["key"])
            t0 = time.time()
            entry["checks"] = evaluate_level(game, model, entry["key"], games.CHECKS[game], eval_games,
                                             CHECK_SEED[game], pool=pool)
            entry["check_seconds"] = round(time.time() - t0, 1)
            log(f"{entry['name']}: " + ", ".join(f"{k} {v['wins']}/{v['draws']}/{v['losses']}"
                                                 for k, v in entry["checks"].items()))
            write_passport(game, passport, out_dir)
    return passport


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m game.train", description="Обучение сети самоигрой (TD-Leaf)")
    ap.add_argument("--game", choices=games.GAMES, required=True)
    ap.add_argument("--threads", type=int, default=4, help="процессов самоигры (по одному потоку)")
    ap.add_argument("--games", type=int, help="сколько партий (по умолчанию - из пресета)")
    ap.add_argument("--minutes", type=float, help="остановиться через столько минут (снимок остаётся)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--run", help="папка журнала и снимков (по умолчанию %%LOCALAPPDATA%%\\ChessCheckersAi\\runs)")
    ap.add_argument("--out", default=models.models_dir(), help="куда положить модели и паспорт")
    ap.add_argument("--eval-games", type=int, default=200)
    ap.add_argument("--recheck", action="store_true", help="не учить, а заново проверить уровни в --out")
    ap.add_argument("--no-finish", action="store_true", help="не проверять и не сохранять модели в конце")
    ap.add_argument("--set", action="append", default=[], metavar="КЛЮЧ=ЗНАЧЕНИЕ",
                    help="поменять настройку пресета, например depth=3")
    args = ap.parse_args(argv)
    if args.recheck:
        recheck(args.game, args.out, args.threads, args.eval_games)
        return 0
    overrides = {}
    for item in args.set:
        k, v = item.split("=", 1)
        overrides[k] = json.loads(v)
    run_dir = args.run or default_run_dir(args.game)
    trainer = Trainer(args.game, run_dir, args.out, threads=args.threads, seed=args.seed, **overrides)
    trainer.resume()
    total = args.games or trainer.cfg["games"]
    done = trainer.played >= total or trainer.run(total=total, stop_after=args.minutes * 60 if args.minutes else None)
    if done and not args.no_finish:
        trainer.finish(args.eval_games)
        trainer.log("готово")
    return 0


if __name__ == "__main__":
    sys.exit(main())
