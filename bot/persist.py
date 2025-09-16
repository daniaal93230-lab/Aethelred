# bot/persist.py
from __future__ import annotations
import json

def save_tuner(path: str, tuner) -> None:
    ser = {}
    for key, trials in tuner.memory.items():
        k = "|".join(map(str, key))  # (symbol, tf, regime, strat) → "sym|tf|regime|strat"
        ser[k] = [{"strat": t.strat, "params": t.params, "score": float(t.score)} for t in trials]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ser, f, indent=2)

def load_tuner(path: str, tuner) -> None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return
    from bot.auto_tuner import Trial  # reuse your dataclass
    for k, arr in data.items():
        key = tuple(k.split("|"))
        for t in arr:
            tuner.memory[key].append(Trial(t["strat"], t["params"], t["score"], metrics={}))
