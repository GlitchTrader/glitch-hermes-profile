"""Bounded offline feature discovery. No network, runtime imports or model export.

Candidate changes use expanding chronological development folds. Confirmation is
excluded from feedback and selection; retaining a feature never grants authority.
Scientific dependencies are imported only by the fitting functions.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime

HORIZONS = (15, 30, 60)
CLASSES = ("UP", "DOWN", "FLAT")
COMPACT_FEATURES = (
    "return_5m_atr15", "return_15m_atr15", "return_60m_atr15",
    "efficiency_5m", "efficiency_15m", "efficiency_60m",
    "tf5_clv", "tf15_clv", "tf60_clv", "tf15_adx", "tf60_adx",
    "tf15_rsi", "tf60_rsi", "tf15_price_to_mean_atr", "tf60_price_to_mean_atr",
    "distance_session_high_atr15", "distance_session_low_atr15",
    "utc_hour_sin", "utc_hour_cos", "instrument_MES", "instrument_MNQ", "instrument_M2K",
)
FOLDS = (("2024-04-02", "2024-07-01"), ("2024-07-02", "2024-10-01"),
         ("2024-10-02", "2024-12-31"))


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def partition(rows, start, end, horizon=60, purge_seconds=86400):
    """Strict time and label-window purge; all instruments share each boundary."""
    lower, upper = timestamp(start + "T00:00:00Z"), timestamp(end + "T00:00:00Z")
    fit, score = [], []
    for index, row in enumerate(rows):
        ts = timestamp(row["utc"])
        if ts + horizon * 60 < lower - purge_seconds:
            fit.append(index)
        elif lower <= ts and ts + horizon * 60 < upper:
            score.append(index)
    return fit, score


def validate_development(rows):
    if len({r["observation_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate_observation")
    if any(r["split"] != "train" or not "2024-01-12" <= r["day"] < "2024-12-31" for r in rows):
        raise ValueError("feedback_outside_development")


def probability(record, name):
    """Noul is a yes probability. Never normalize independent questions together."""
    if record.get("status") != "ok" or record.get("returned_model") != "jev-1.13.0":
        return None
    answer = record.get("response", {}).get("answers", {}).get(name, {})
    value = answer.get("noul")
    if answer.get("type") != "noul" or type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return value


def accept_change(before, after, minimum_gain=.002, max_horizon_damage=.003):
    """Predeclared conservative development screen, not a statistical edge claim."""
    if set(before) != set(after) or not before:
        raise ValueError("unmatched_scores")
    deltas = {k: after[k] - before[k] for k in before}
    if not all(math.isfinite(v) for v in deltas.values()):
        raise ValueError("nonfinite_score")
    folds = sorted({k.split(":")[0] for k in deltas})
    horizons = sorted({k.split(":")[1] for k in deltas})
    mean = sum(deltas.values()) / len(deltas)
    improved = sum(sum(v for k, v in deltas.items() if k.split(":")[0] == f) < 0 for f in folds)
    worst = max(sum(v for k, v in deltas.items() if k.split(":")[1] == h) / len(folds) for h in horizons)
    return {"accepted": mean <= -minimum_gain and improved >= 2 and worst <= max_horizon_damage,
            "mean_brier_difference": mean, "improved_folds": improved,
            "worst_horizon_difference": worst, "cell_differences": deltas}


def matrix(rows, names=COMPACT_FEATURES, semantic=None, selected=()):
    import numpy as np
    return np.array([[r["features"].get(k) if r["features"].get(k) is not None else np.nan for k in names]
                     + [semantic[r["observation_id"]][k] for k in selected] for r in rows], dtype=float)


def fit_predict(train_x, train_y, score_x, kind="logistic"):
    import numpy as np
    from sklearn.pipeline import make_pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.tree import DecisionTreeClassifier
    if len(set(train_y)) < 2 or kind == "frequency":
        p = np.bincount(train_y, minlength=3) / len(train_y)
        return np.tile(p, (len(score_x), 1))
    estimator = (DecisionTreeClassifier(max_depth=3, min_samples_leaf=max(20, math.ceil(len(train_y)*.01)), random_state=0)
                 if kind == "tree" else LogisticRegression(C=.1, max_iter=2000, random_state=0))
    model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler(), estimator)
    model.fit(train_x, train_y)
    out = np.zeros((len(score_x), 3))
    predicted = model.predict_proba(score_x)
    for index, value in enumerate(model.classes_):
        out[:, int(value)] = predicted[:, index]
    return out


def evaluate(rows, labels, semantic, selected=(), names=COMPACT_FEATURES, kind="logistic", folds=FOLDS):
    import numpy as np
    if folds == FOLDS:
        validate_development(rows)
    x = matrix(rows, names, semantic, selected)
    cells, scored = {}, []
    for h in HORIZONS:
        usable = [i for i, r in enumerate(rows) if labels[r["observation_id"]][str(h)]["status"] == "ok"]
        y = {i: CLASSES.index(labels[rows[i]["observation_id"]][str(h)]["label"]) for i in usable}
        for fold, (start, end) in enumerate(folds):
            tr, te = partition(rows, start, end, h)
            tr, te = [i for i in tr if i in y], [i for i in te if i in y]
            if len(tr) < 100 or not te:
                raise ValueError("insufficient_chronological_fold")
            p = fit_predict(x[tr], [y[i] for i in tr], x[te], kind)
            losses = ((p - np.eye(3)[[y[i] for i in te]]) ** 2).sum(axis=1)
            cells[f"{fold}:{h}"] = float(losses.mean())
            for i, prob, loss in zip(te, p, losses):
                r = rows[i]
                scored.append({"observation_id": r["observation_id"], "day": r["day"], "root": r["root"],
                               "fold": fold, "horizon": h, "truth": CLASSES[y[i]],
                               "probabilities": dict(zip(CLASSES, prob.tolist())), "brier": float(loss), "fit_n": len(tr)})
    return cells, scored


def feedback(rows, scored, selected, limit=12):
    """Only causal development errors may be shown to the question proposer."""
    validate_development(rows)
    lookup = {r["observation_id"]: r for r in rows}
    if any(s["observation_id"] not in lookup for s in scored):
        raise ValueError("foreign_feedback_row")
    grouped = {}
    for score in scored:
        grouped.setdefault(score["observation_id"], []).append(score)
    ranked = sorted(grouped, key=lambda k: (-sum(s["brier"] for s in grouped[k])/len(grouped[k]), k))
    chosen = list(dict.fromkeys(ranked[:limit//2] + ranked[-limit//2:]))
    return {"scope": "2024 chronological development errors only; no confirmation labels", "selected": selected,
            "examples": [{"observation_id": k, "scores": grouped[k], "state": lookup[k]["state"]} for k in chosen]}
