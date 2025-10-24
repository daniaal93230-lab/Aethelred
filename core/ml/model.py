import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold
from joblib import dump


def build_dataset(decisions):
    """Build a simple dataset from decision_log rows for an entry gating model.
    decisions: iterable of rows or (ts,symbol,...) tuples
    Returns X, y, meta
    """
    cols = [
        "ts","symbol","strategy","regime","signal","intent","size_usd","price","ml_p_up","ml_vote","veto","reasons","planned_stop","planned_tp","run_id"
    ]
    try:
        df = pd.DataFrame(decisions, columns=cols)
    except Exception:
        df = pd.DataFrame(decisions)
    if df.empty:
        return np.zeros((0,1)), np.zeros((0,), dtype=int), {"n": 0}
    # Binary target: intent is entry (buy/sell) vs hold
    df["y"] = df["intent"].isin(["buy","sell"]).astype(int)
    # Features: one-hots on strategy/regime; ml_p_up; z-scored size
    X = pd.get_dummies(df[["strategy","regime"]].astype(str), drop_first=True)
    mp = pd.to_numeric(df.get("ml_p_up", 0.5), errors="coerce").fillna(0.5)
    X["ml_p_up"] = mp
    sz = pd.to_numeric(df.get("size_usd", 0.0), errors="coerce").fillna(0.0)
    X["size_z"] = (sz - sz.mean()) / (sz.std() + 1e-9)
    return X.values, df["y"].values, {"n": int(len(df))}


ess = None


def train_model(X, y):
    if X.shape[0] == 0:
        # trivial fallback classifier storing prior
        global ess
        ess = float(np.mean(y)) if y.size else 0.0
        return None, {"classes": [], "n": 0}
    n_splits = int(min(5, max(2, len(np.unique(y)))))
    base = LogisticRegression(max_iter=200, class_weight="balanced")
    clf = CalibratedClassifierCV(base, method="isotonic", cv=n_splits)
    clf.fit(X, y)
    return clf, {"classes": np.bincount(y).tolist(), "n": int(y.size)}


def save_model(model, path):
    dump(model, path)
