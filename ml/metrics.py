from __future__ import annotations
import numpy as np
from typing import Tuple, Dict


def expected_calibration_error(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 15,
) -> float:
    """ECE with equal-width bins in [0,1]."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.digitize(y_prob, bins) - 1
    idx = np.clip(idx, 0, n_bins - 1)
    ece: float = 0.0
    for b in range(n_bins):
        mask = idx == b
        if not np.any(mask):
            continue
        conf = float(np.mean(y_prob[mask]))
        acc = float(np.mean(y_true[mask]))
        w = float(np.mean(mask.astype(float)))
        ece += w * abs(acc - conf)
    return float(ece)


def tune_threshold_by_ece(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    grid: np.ndarray | None = None,
) -> Tuple[float, Dict[str, float]]:
    """
    Choose decision threshold that minimizes validation ECE while keeping precision/recall balanced.
    Returns threshold and metrics.
    """
    if grid is None:
        grid = np.linspace(0.2, 0.8, 25)
    best = None
    best_t = 0.5
    best_metrics: Dict[str, float] = {"ece": 0.0, "precision": 0.0, "recall": 0.0}
    from sklearn.metrics import precision_score, recall_score

    for t in grid:
        y_hat = (y_prob >= t).astype(int)
        ece = expected_calibration_error(y_true, y_prob)
        prec = precision_score(y_true, y_hat, zero_division=0)
        rec = recall_score(y_true, y_hat, zero_division=0)
        bal = 1.0 - abs(prec - rec)  # closer to 1 is better balance
        score = -ece + 0.05 * bal
        if best is None or score > best:
            best = score
            best_t = float(t)
            best_metrics = {"ece": float(ece), "precision": float(prec), "recall": float(rec)}
    return best_t, best_metrics
