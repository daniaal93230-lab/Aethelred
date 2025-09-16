# bot/auto_tuner.py
from __future__ import annotations
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple, Callable, Any

@dataclass
class Trial:
    strat: str
    params: Dict[str, Any]
    score: float
    metrics: Dict[str, Any]

class AutoTuner:
    """
    Lightweight tuner:
      - random warm start guided by simple priors
      - successive halving across increasing test fraction (0.25 → 0.5 → 1.0)
      - persistent in-memory priors by (symbol, tf, regime, strat)
    """
    def __init__(self, budget: int = 40, r_start: float = 0.25, r_halve: int = 3):
        self.budget = budget
        self.r_start = r_start
        self.r_halve = max(2, r_halve)
        self.memory = defaultdict(list)  # key=(symbol,tf,regime,strat) -> [Trial]

    def _flat_params(self, grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        # simple cartesian product
        items = list(grid.items())
        if not items:
            return [{}]
        res = [{}]
        for k, vals in items:
            nxt = []
            for r in res:
                for v in vals:
                    rr = dict(r); rr[k] = v
                    nxt.append(rr)
            res = nxt
        return res

    def _seed_candidates(self, key_base, strat_grids: List[Tuple[str, Dict[str, List[Any]]]], warm_k: int) -> List[Tuple[str, Dict[str, Any]]]:
        # Order strategies by prior mean score, then sample one param set per pass
        pri = []
        for strat, grid in strat_grids:
            past = self.memory[key_base + (strat,)]
            mean = sum(t.score for t in past)/len(past) if past else 0.0
            pri.append((mean + random.random()*0.05, strat, grid))
        pri.sort(reverse=True)

        seeds: List[Tuple[str, Dict[str, Any]]] = []
        cursors = {s: self._flat_params(g) for _, s, g in [(None, x[1], x[2]) for x in pri]}
        for _, strat, grid in pri:
            random.shuffle(cursors[strat])
        while len(seeds) < warm_k:
            progressed = False
            for _, strat, _ in pri:
                pool = cursors[strat]
                if pool:
                    seeds.append((strat, pool.pop()))
                    progressed = True
                    if len(seeds) >= warm_k:
                        break
            if not progressed:
                break
        return seeds

    def _score(self, m: Dict[str, Any]) -> float:
        # Composite: prioritize Sharpe, penalize DD, reward trades a bit
        sharpe = float(m.get("sharpe", -999))
        dd = float(m.get("max_dd", 0.5))
        ntr = int(m.get("n_trades", 0))
        return sharpe - 0.10*dd + 0.001*ntr

    def tune_segment(
        self,
        key_base: Tuple[str, str, str],  # (symbol, tf, regime)
        strat_grids: List[Tuple[str, Dict[str, List[Any]]]],
        eval_fn: Callable[[str, Dict[str, Any], Any, Any, float], Dict[str, Any]],
        train_df,
        test_df,
    ) -> Tuple[Trial | None, List[Trial]]:
        B = self.budget
        if not strat_grids or B <= 0:
            return None, []

        # Warm seeds
        warm_k = max(6, min(16, B // 2))
        remain = self._seed_candidates(key_base, strat_grids, warm_k)
        trials: List[Trial] = []
        frac = self.r_start

        while remain and B > 0:
            batch = remain[:min(len(remain), B)]
            scored: List[Trial] = []
            for strat, params in batch:
                m = eval_fn(strat, params, train_df, test_df, frac_len=frac)
                scored.append(Trial(strat, params, self._score(m), m))
            B -= len(batch)
            scored.sort(key=lambda t: t.score, reverse=True)
            trials.extend(scored)
            # keep top 1/r_halve for next round
            k_keep = max(1, len(scored) // self.r_halve)
            remain = [(t.strat, t.params) for t in scored[:k_keep]]
            frac = min(1.0, frac * 2.0)
            if frac >= 1.0 and len(remain) <= 1:
                break

        best = max(trials, key=lambda t: t.score) if trials else None
        if best:
            self.memory[key_base + (best.strat,)].append(best)
        return best, trials
