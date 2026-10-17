"""
OrbitGuard - check the ML risk model against real SOCRATES conjunctions
------------------------------------------------------------------------
The Random Forest in ml_risk.py is trained on SYNTHETIC labels. This script compares what it
says about real close approaches with CelesTrak's SOCRATES screening results, so you can see
where it agrees and where it does not.

    1. Download a SOCRATES result as CSV from https://celestrak.org/SOCRATES (the column layout is
       documented at https://www.celestrak.org/SOCRATES/socrates-format.php). Use a fresh download:
       the TCAs are then in the next 7 days and today's TLEs are valid for them.
    2. python validate_socrates.py socrates.csv
       python validate_socrates.py socrates.csv --out report.json --rows-out rows.csv
       python validate_socrates.py socrates.csv --no-tle-lookup      # offline; altitude falls back to 500 km

What is compared. SOCRATES gives, per conjunction, the miss distance (TCA_RANGE), the relative
speed (TCA_RELATIVE_SPEED) and MAX_PROB, an upper-bound collision probability. The model needs those
two numbers plus the objects' altitudes; SOCRATES has none, so (unless --no-tle-lookup) the script
fetches both objects' current TLEs from CelesTrak and propagates them to the TCA to get altitudes.
MAX_PROB is turned into reference labels (HIGH >= 1e-4, MEDIUM >= 1e-5 by default, change with
--high-pc / --medium-pc) and the report shows:
  * accuracy and a confusion matrix for the ML level and for the old distance-only rule,
  * Spearman rank correlation between each score and log10(MAX_PROB), with miss distance alone as the
    baseline the ML score has to beat to be worth anything,
  * AUC for picking out the higher-risk events,
  * the MAX_PROB range seen in each ML class.

What this does NOT show. MAX_PROB is a screening estimate from public TLEs, not a record of collisions
(nobody publishes those), and SOCRATES's own page calls it conservative. SOCRATES only lists events
within 5 km, so the sample is a narrow slice of what the model sees. Good agreement would be encouraging,
not proof; poor agreement is a real finding about the synthetic labels.

Units are not stated on the SOCRATES pages this script was written from. It assumes km and km/s and warns
when the numbers look like metres; set --range-unit m / --speed-unit m/s if yours are.
"""

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support, roc_auc_score

import cache
import conjunction
import ml_risk
import orbit_engine as engine

CLASSES = ml_risk.CLASSES                       # ["LOW", "MEDIUM", "HIGH"]
REQUIRED_COLUMNS = ("TCA_RANGE", "TCA_RELATIVE_SPEED", "MAX_PROB")
DEFAULT_HIGH_PC = 1e-4
DEFAULT_MEDIUM_PC = 1e-5
SMALL_SAMPLE = 30
TCA_FORMATS = ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f",
               "%Y-%m-%d %H:%M:%S", "%Y %b %d %H:%M:%S.%f", "%Y %b %d %H:%M:%S")

CAVEATS = [
    "MAX_PROB is a conservative screening estimate from public TLEs, not a record of collision outcomes.",
    "SOCRATES lists only events within 5 km, so this is a narrow slice of what the model scores.",
    "Altitudes are estimated from today's TLEs propagated to the TCA, not supplied by SOCRATES.",
]


# ----------------------------------------------------------------------------
# reading the CSV
# ----------------------------------------------------------------------------
def parse_tca(text: str | None) -> datetime | None:
    """TCA as a UTC datetime, or None when the format is not recognised (the docs do not state one)."""
    raw = (text or "").strip().rstrip("Z")
    for fmt in TCA_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _norm(name: str) -> str:
    return name.strip().upper().replace(" ", "_")


def _int_or_none(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def load_socrates_csv(path, range_unit: str = "km", speed_unit: str = "km/s") -> tuple[list[dict], Counter]:
    """
    Read a SOCRATES CSV. Returns (rows, dropped) where dropped counts rows that could not be used by reason.
    Rows are dicts with range_km, speed_km_s, max_prob and (when present) ids, names, tca.
    """
    range_scale = {"km": 1.0, "m": 1e-3}[range_unit]
    speed_scale = {"km/s": 1.0, "m/s": 1e-3}[speed_unit]
    text = Path(path).read_text(encoding="utf-8-sig")
    reader = csv.DictReader(text.splitlines(), skipinitialspace=True)
    if not reader.fieldnames:
        raise SystemExit(f"{path} is empty.")
    reader.fieldnames = [_norm(n) for n in reader.fieldnames]
    missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise SystemExit(
            f"{path} has no {', '.join(missing)} column. Expected the SOCRATES CSV with a header row "
            f"(NORAD_CAT_ID_1, ..., TCA, TCA_RANGE, TCA_RELATIVE_SPEED, MAX_PROB, DILUTION). "
            f"Found: {', '.join(reader.fieldnames)}. The legacy .txt files have no header and are not supported.")

    rows, dropped = [], Counter()
    for rec in reader:
        try:
            rng = float(rec["TCA_RANGE"]) * range_scale
            spd = float(rec["TCA_RELATIVE_SPEED"]) * speed_scale
            pc = float(rec["MAX_PROB"])
        except (TypeError, ValueError):
            dropped["unreadable number"] += 1
            continue
        if not all(math.isfinite(v) for v in (rng, spd, pc)):
            dropped["unreadable number"] += 1
        elif rng < 0 or spd < 0:
            dropped["negative range or speed"] += 1
        elif pc <= 0:
            dropped["MAX_PROB is zero or negative"] += 1
        else:
            rows.append({
                "norad_1": _int_or_none(rec.get("NORAD_CAT_ID_1")), "norad_2": _int_or_none(rec.get("NORAD_CAT_ID_2")),
                "name_1": (rec.get("OBJECT_NAME_1") or "").strip(), "name_2": (rec.get("OBJECT_NAME_2") or "").strip(),
                "tca": parse_tca(rec.get("TCA")), "range_km": rng, "speed_km_s": spd, "max_prob": pc,
            })
    return rows, dropped


def check_units(rows: list[dict]) -> list[str]:
    """Warnings when the numbers look like the wrong unit (SOCRATES screens within 5 km; LEO speeds are < ~16 km/s)."""
    out = []
    if rows:
        if statistics.median(r["range_km"] for r in rows) > 50:
            out.append("Median TCA_RANGE is above 50 km but SOCRATES screens within 5 km: the file is probably in "
                       "metres. Re-run with --range-unit m.")
        if max(r["speed_km_s"] for r in rows) > 20:
            out.append("Relative speeds above 20 km/s are not physical for Earth orbit: the file is probably in m/s. "
                       "Re-run with --speed-unit m/s.")
    return out


# ----------------------------------------------------------------------------
# features the model needs but SOCRATES does not give: altitudes
# ----------------------------------------------------------------------------
def estimate_altitudes(rows: list[dict], fetch_fn=None) -> list[dict]:
    """
    Per row: {"object_1": km|None, "object_2": km|None, "source": "tle_at_tca" | "tle_at_now" | "fallback"}.
    Uses today's TLE for each object propagated to the TCA ("tle_at_now" when the TCA could not be parsed).
    Anything that cannot be fetched or propagated falls back (None, so ml_risk applies its 500 km default).
    """
    fetch_fn = fetch_fn or engine.fetch_tle
    ids = sorted({n for r in rows for n in (r["norad_1"], r["norad_2"]) if n is not None})
    tles, errors = {}, {}
    if ids:
        tles, errors, _ = cache.get_tles_by_ids(ids, fetch_fn)

    def altitude(nid, when):
        if nid is None or nid not in tles:
            return None
        try:
            return engine.propagate(tles[nid], when)["altitude_km"]
        except Exception:
            return None

    out = []
    for r in rows:
        when = r["tca"] or datetime.now(timezone.utc)
        a1, a2 = altitude(r["norad_1"], when), altitude(r["norad_2"], when)
        if a1 is None or a2 is None:
            out.append({"object_1": None, "object_2": None, "source": "fallback"})
        else:
            out.append({"object_1": a1, "object_2": a2, "source": "tle_at_tca" if r["tca"] else "tle_at_now"})
    return out


# ----------------------------------------------------------------------------
# evaluation
# ----------------------------------------------------------------------------
def reference_label(max_prob: float, high_pc: float, medium_pc: float) -> int:
    """0 = LOW, 1 = MEDIUM, 2 = HIGH from SOCRATES's MAX_PROB."""
    return 2 if max_prob >= high_pc else 1 if max_prob >= medium_pc else 0


def _spearman(x, y) -> dict | None:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    res = spearmanr(x, y)
    return {"rho": round(float(res.statistic), 4), "p_value": float(res.pvalue)}


def _auc(ref, score, at_least: int) -> float | None:
    y = (np.asarray(ref) >= at_least).astype(int)
    if y.min() == y.max():
        return None
    return round(float(roc_auc_score(y, score)), 4)


def _classification(ref, pred) -> dict:
    labels = [0, 1, 2]
    p, r, _, support = precision_recall_fscore_support(ref, pred, labels=labels, zero_division=0)
    return {
        "accuracy": round(float(accuracy_score(ref, pred)), 4),
        "confusion_matrix": {"rows_are": "reference (SOCRATES MAX_PROB)", "columns_are": "predicted",
                             "labels": CLASSES, "counts": confusion_matrix(ref, pred, labels=labels).tolist()},
        "per_class": {CLASSES[i]: {"precision": round(float(p[i]), 3), "recall": round(float(r[i]), 3),
                                   "reference_count": int(support[i])} for i in labels},
    }


def score_rows(rows: list[dict], altitudes: list[dict]) -> list[dict]:
    """Run the ML model on every row; returns conjunction dicts with ml_risk_level / ml_risk_score added."""
    conjs = [{"distance_km": r["range_km"], "relative_velocity_km_s": r["speed_km_s"],
              "altitude_km": {"object_1": a["object_1"], "object_2": a["object_2"]}}
             for r, a in zip(rows, altitudes)]
    return ml_risk.score_conjunctions(conjs)


def evaluate(rows: list[dict], altitudes: list[dict], high_pc: float = DEFAULT_HIGH_PC,
             medium_pc: float = DEFAULT_MEDIUM_PC, scored: list[dict] | None = None) -> dict:
    """Compare the ML model with the SOCRATES-derived reference. Returns the report dict.
    `scored` is the output of score_rows(), when the caller already has it."""
    if not rows:
        raise SystemExit("No usable rows in the file, nothing to evaluate.")
    conjs = scored if scored is not None else score_rows(rows, altitudes)

    pc = np.array([r["max_prob"] for r in rows])
    logpc = np.log10(pc)
    dist = np.array([r["range_km"] for r in rows])
    ref = [reference_label(p, high_pc, medium_pc) for p in pc]
    ml_pred = [CLASSES.index(c["ml_risk_level"]) for c in conjs]
    rule_pred = [CLASSES.index(conjunction._risk_level(d)) for d in dist]
    ml_score = np.array([c["ml_risk_score"] for c in conjs])

    rho_ml, rho_dist = _spearman(ml_score, logpc), _spearman(-dist, logpc)
    by_level = {}
    for i, name in enumerate(CLASSES):
        vals = pc[[k for k, c in enumerate(ml_pred) if c == i]]
        by_level[name] = ({"count": int(len(vals)), "max_prob_median": float(np.median(vals)),
                           "max_prob_min": float(vals.min()), "max_prob_max": float(vals.max())}
                          if len(vals) else {"count": 0})
    sources = Counter(a["source"] for a in altitudes)

    notes = []
    if len(rows) < SMALL_SAMPLE:
        notes.append(f"Only {len(rows)} conjunctions: correlations and AUC are unstable, read them as indicative.")
    if len(set(ref)) == 1:
        notes.append(f"Every row falls in one reference class ({CLASSES[ref[0]]}) at these thresholds, so accuracy "
                     "and AUC say little. Lower --high-pc / --medium-pc or use a file with more spread.")
    if rho_ml and rho_dist:
        gap = rho_ml["rho"] - rho_dist["rho"]
        notes.append("The ML score ranks MAX_PROB " + (
            f"better than miss distance alone (Spearman {rho_ml['rho']:+.2f} vs {rho_dist['rho']:+.2f})." if gap > 0.02
            else f"no better than miss distance alone (Spearman {rho_ml['rho']:+.2f} vs {rho_dist['rho']:+.2f})."))
    if sources.get("fallback"):
        notes.append(f"{sources['fallback']} of {len(rows)} rows used the 500 km altitude fallback "
                     "(TLE missing, ids absent, or propagation failed); the model's altitude inputs are weak for those.")
    far = sum(1 for r in rows if r["tca"] and abs((r["tca"] - datetime.now(timezone.utc)).days) > 7)
    if far:
        notes.append(f"{far} rows have a TCA more than 7 days from today; today's TLEs are less reliable there. "
                     "Use a fresh download.")

    return {
        "n_rows": len(rows),
        "thresholds": {"high_if_max_prob_at_least": high_pc, "medium_if_max_prob_at_least": medium_pc},
        "reference_class_counts": {CLASSES[i]: ref.count(i) for i in range(3)},
        "altitude_source_counts": dict(sources),
        "ml_model": _classification(ref, ml_pred),
        "distance_rule_baseline": _classification(ref, rule_pred),
        "rank_correlation_with_log10_max_prob": {"ml_score": rho_ml, "negative_miss_distance_baseline": rho_dist},
        "auc": {
            "ml_score_high_vs_rest": _auc(ref, ml_score, 2),
            "ml_score_medium_or_high_vs_low": _auc(ref, ml_score, 1),
            "negative_miss_distance_high_vs_rest": _auc(ref, -dist, 2),
            "negative_miss_distance_medium_or_high_vs_low": _auc(ref, -dist, 1),
        },
        "max_prob_by_predicted_ml_level": by_level,
        "notes": notes,
        "caveats": CAVEATS,
        "model_training_labels": "synthetic (see ml_risk.py)",
    }


def format_summary(rep: dict) -> str:
    def fmt(x):
        return "n/a" if x is None else f"{x:.3f}" if isinstance(x, float) else str(x)

    lines = [f"SOCRATES check on {rep['n_rows']} conjunctions "
             f"(reference: HIGH if MAX_PROB >= {rep['thresholds']['high_if_max_prob_at_least']:g}, "
             f"MEDIUM if >= {rep['thresholds']['medium_if_max_prob_at_least']:g})",
             f"  reference classes: {rep['reference_class_counts']}",
             f"  altitude source:   {rep['altitude_source_counts']}", ""]
    for key, title in (("ml_model", "ML model"), ("distance_rule_baseline", "Distance rule (<1 km HIGH, <5 km MEDIUM)")):
        m = rep[key]
        lines.append(f"{title}: accuracy {m['accuracy']:.3f}")
        lines.append(f"  confusion (rows = SOCRATES, cols = predicted {CLASSES}): {m['confusion_matrix']['counts']}")
    rc = rep["rank_correlation_with_log10_max_prob"]
    lines += ["", "Spearman correlation with log10(MAX_PROB):",
              f"  ML score:               {fmt(rc['ml_score'] and rc['ml_score']['rho'])}",
              f"  -miss distance (alone): {fmt(rc['negative_miss_distance_baseline'] and rc['negative_miss_distance_baseline']['rho'])}",
              "", "AUC: " + ", ".join(f"{k}={fmt(v)}" for k, v in rep["auc"].items()), "",
              "MAX_PROB by predicted ML level:"]
    for name, v in rep["max_prob_by_predicted_ml_level"].items():
        lines.append(f"  {name}: n={v['count']}" + (f", median {v['max_prob_median']:.2e} "
                     f"(range {v['max_prob_min']:.2e} to {v['max_prob_max']:.2e})" if v["count"] else ""))
    lines += ["", "Notes:"] + [f"  - {n}" for n in rep["notes"]] + ["", "Caveats:"] + [f"  - {c}" for c in rep["caveats"]]
    return "\n".join(lines)


def write_rows_csv(path, rows, altitudes, report_rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["norad_1", "norad_2", "tca_utc", "range_km", "speed_km_s", "max_prob", "reference",
                    "altitude_1_km", "altitude_2_km", "altitude_source", "ml_level", "ml_score"])
        for r, a, c in zip(rows, altitudes, report_rows):
            w.writerow([r["norad_1"], r["norad_2"], r["tca"].isoformat() if r["tca"] else "", r["range_km"],
                        r["speed_km_s"], r["max_prob"], c["reference"], a["object_1"], a["object_2"], a["source"],
                        c["ml_risk_level"], c["ml_risk_score"]])


# ----------------------------------------------------------------------------
# command line
# ----------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare the ML risk model with a SOCRATES CSV.")
    ap.add_argument("csv", type=Path, help="SOCRATES result as CSV (with the header row)")
    ap.add_argument("--high-pc", type=float, default=DEFAULT_HIGH_PC, help="MAX_PROB at or above this is HIGH (1e-4)")
    ap.add_argument("--medium-pc", type=float, default=DEFAULT_MEDIUM_PC, help="MAX_PROB at or above this is MEDIUM (1e-5)")
    ap.add_argument("--range-unit", choices=["km", "m"], default="km")
    ap.add_argument("--speed-unit", choices=["km/s", "m/s"], default="km/s")
    ap.add_argument("--no-tle-lookup", action="store_true",
                    help="do not fetch TLEs from CelesTrak; every row uses the 500 km altitude fallback")
    ap.add_argument("--out", type=Path, help="write the full report as JSON")
    ap.add_argument("--rows-out", type=Path, help="write one line per conjunction (features, labels, predictions) as CSV")
    args = ap.parse_args(argv)
    if not (0 < args.medium_pc < args.high_pc <= 1):
        ap.error("need 0 < --medium-pc < --high-pc <= 1")

    rows, dropped = load_socrates_csv(args.csv, args.range_unit, args.speed_unit)
    for w in check_units(rows):
        print("WARNING:", w, file=sys.stderr)
    if dropped:
        print("Dropped rows:", dict(dropped), file=sys.stderr)

    if args.no_tle_lookup:
        altitudes = [{"object_1": None, "object_2": None, "source": "fallback"} for _ in rows]
    else:
        altitudes = estimate_altitudes(rows)

    if not rows:
        raise SystemExit("No usable rows in the file, nothing to evaluate.")
    scored = score_rows(rows, altitudes)
    report = evaluate(rows, altitudes, args.high_pc, args.medium_pc, scored=scored)
    report["dropped_rows"] = dict(dropped)
    print(format_summary(report))
    if args.out:
        args.out.write_text(json.dumps(report, indent=2))
        print(f"\nFull report written to {args.out}")
    if args.rows_out:
        for r, c in zip(rows, scored):
            c["reference"] = CLASSES[reference_label(r["max_prob"], args.high_pc, args.medium_pc)]
        write_rows_csv(args.rows_out, rows, altitudes, scored)
        print(f"Per-conjunction rows written to {args.rows_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
