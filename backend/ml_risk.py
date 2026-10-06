"""
OrbitGuard - ML-based risk scoring
-----------------------------------
A Random Forest classifier that scores each conjunction as LOW / MEDIUM / HIGH
using more than distance alone: it also looks at relative velocity (impact
energy) and orbital altitude (debris density differs by orbit band).

IMPORTANT (be upfront about this in your report/viva):
There is no public dataset of labelled "this pair really collided" events, so
the training labels here are SYNTHETIC. They come from a physics-inspired risk
formula plus random noise (see _synthetic_risk). The model therefore learns a
smooth, multi-feature approximation of that formula; it is NOT validated
against real collision outcomes. The honest framing is "ML risk scoring
framework, ready to be retrained on real conjunction data (e.g. CDMs)".

The model is trained automatically on first use and cached in models/.
Retrain manually with:  python ml_risk.py
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

MODEL_DIR = Path(__file__).parent / "models"
MODEL_PATH = MODEL_DIR / "risk_model.joblib"
METRICS_PATH = MODEL_DIR / "risk_model_metrics.json"

FEATURES = [
    "distance_km",
    "relative_velocity_km_s",
    "mean_altitude_km",
    "altitude_gap_km",
]
CLASSES = ["LOW", "MEDIUM", "HIGH"]
RNG_SEED = 42
N_SAMPLES = 20000

_model = None  # lazily loaded


# ---------- synthetic training data ----------

def _synthetic_risk(distance, velocity, mean_alt, alt_gap, rng):
    """
    Physics-inspired risk in [0, 1]:
      - closer approach => much higher risk (Gaussian falloff, ~2 km scale)
      - faster relative speed => more severe/less time to react
      - altitude bands with dense debris (~700-1000 km) => slight bump
      - big altitude gap => objects are on different shells, lower risk
    plus noise so the forest learns a smooth boundary, not a hard rule.
    """
    proximity = np.exp(-(distance / 2.0) ** 2)
    speed = np.clip(velocity / 10.0, 0.2, 1.3)
    density = 1.0 + 0.25 * np.exp(-((mean_alt - 850.0) / 250.0) ** 2)
    shell = 1.0 / (1.0 + (alt_gap / 20.0) ** 2)
    risk = proximity * (0.5 + 0.5 * speed) * density * (0.6 + 0.4 * shell)
    risk = risk + rng.normal(0, 0.03, size=risk.shape)
    return np.clip(risk, 0.0, 1.0)


def _label(risk):
    return np.where(risk >= 0.45, 2, np.where(risk >= 0.12, 1, 0))


def _generate_dataset(n=N_SAMPLES, seed=RNG_SEED):
    rng = np.random.default_rng(seed)
    # Oversample close approaches: that's where the interesting decisions are.
    close = rng.exponential(2.0, size=n // 2)
    far = rng.uniform(0, 15, size=n - n // 2)
    distance = np.clip(np.concatenate([close, far]), 0.001, 15)
    velocity = rng.uniform(0.0, 15.0, size=n)          # km/s relative speed
    mean_alt = rng.uniform(300, 2000, size=n)           # LEO range
    alt_gap = np.abs(rng.exponential(10.0, size=n))
    risk = _synthetic_risk(distance, velocity, mean_alt, alt_gap, rng)
    X = np.column_stack([distance, velocity, mean_alt, alt_gap])
    return X, _label(risk)


# ---------- training / loading ----------

def train(save: bool = True) -> dict:
    X, y = _generate_dataset()
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=RNG_SEED, stratify=y
    )
    model = RandomForestClassifier(
        n_estimators=150, max_depth=12, random_state=RNG_SEED, n_jobs=-1
    )
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)

    metrics = {
        "model": "RandomForestClassifier",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "label_source": "synthetic (physics-inspired formula + noise); not real collision outcomes",
        "n_samples": int(len(X)),
        "n_estimators": 150,
        "accuracy": round(float(accuracy_score(y_te, pred)), 4),
        "per_class": {
            CLASSES[int(k)]: {m: round(v, 3) for m, v in d.items() if m != "support"} | {"support": int(d["support"])}
            for k, d in classification_report(y_te, pred, output_dict=True, zero_division=0).items()
            if k in ("0", "1", "2")
        },
        "feature_importance": {
            f: round(float(i), 4) for f, i in zip(FEATURES, model.feature_importances_)
        },
        "class_balance": {CLASSES[i]: int((y == i).sum()) for i in range(3)},
    }
    if save:
        MODEL_DIR.mkdir(exist_ok=True)
        joblib.dump(model, MODEL_PATH)
        METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    return {"model": model, "metrics": metrics}


def _get_model():
    global _model
    if _model is None:
        try:
            _model = joblib.load(MODEL_PATH)
        except Exception:
            # Missing or saved with an incompatible sklearn version -> retrain.
            _model = train()["model"]
    return _model


def get_metrics() -> dict:
    _get_model()
    return json.loads(METRICS_PATH.read_text())


# ---------- scoring ----------

def _features_from_conjunction(c: dict) -> list[float]:
    alts = c.get("altitude_km") or {}
    a1, a2 = alts.get("object_1"), alts.get("object_2")
    if a1 is None or a2 is None:
        a1 = a2 = 500.0  # fallback if altitude is unavailable
    return [
        c["distance_km"],
        c["relative_velocity_km_s"],
        (a1 + a2) / 2.0,
        abs(a1 - a2),
    ]


def score_conjunctions(conjunctions: list[dict]) -> list[dict]:
    """Add ml_risk_level, ml_risk_score (0-1) and class probabilities to each conjunction."""
    if not conjunctions:
        return conjunctions
    model = _get_model()
    X = np.array([_features_from_conjunction(c) for c in conjunctions])
    proba = model.predict_proba(X)
    classes = [int(k) for k in model.classes_]
    for c, p in zip(conjunctions, proba):
        pr = {CLASSES[k]: float(v) for k, v in zip(classes, p)}
        level = max(pr, key=pr.get)
        c["ml_risk_level"] = level
        c["ml_risk_score"] = round(pr.get("HIGH", 0.0) + 0.5 * pr.get("MEDIUM", 0.0), 3)
        c["ml_probabilities"] = {k: round(pr.get(k, 0.0), 3) for k in CLASSES}
    return conjunctions


if __name__ == "__main__":
    out = train()
    print(json.dumps(out["metrics"], indent=2))
