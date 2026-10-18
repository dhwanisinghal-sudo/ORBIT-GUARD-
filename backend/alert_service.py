"""
OrbitGuard - watchlist screening, shared by the REST endpoint and the background job
--------------------------------------------------------------------------------------
Screening the catalog is the expensive part (seconds, hundreds of MB), so it is split in two:

    screen(norad_ids, params)           ONE pass for a set of satellites (the union of several
                                        users' watchlists is fine): fetch TLEs, check that each
                                        satellite can be propagated, find its close approaches.
    build_response(watched, scr, p)     cheap, per user: pick out that user's satellites and
                                        conjunctions and describe them.

GET /watchlist/alerts calls both for one user. The background job (alert_hub.py) calls
screen() once for everybody and build_response() once per user.
"""

import copy
from dataclasses import dataclass
from datetime import datetime, timezone

import cache
import conjunction_window as conjw
import forecast_service as svc
import ml_risk
import orbit_engine as engine

RISK_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


@dataclass(frozen=True)
class Params:
    group: str = "active"
    hours: float = 24.0
    threshold_km: float = 5.0
    step_seconds: float = 60.0
    include_coorbiting: bool = False
    ml: bool = False
    start_dt: datetime | None = None      # None = "now" every time (what production wants)


def _norad(tle: dict) -> int | None:
    try:
        return int(tle["line1"][2:7])
    except Exception:
        return None


def screen(norad_ids, p: Params) -> dict:
    """Close approaches involving any of `norad_ids`, screened against the whole group."""
    ids = sorted({int(i) for i in norad_ids})
    ref = p.start_dt or datetime.now(timezone.utc)

    # 1. the watched satellites (cache first, only misses go to CelesTrak)
    wl_tles, wl_errors, _ = cache.get_tles_by_ids(ids, engine.fetch_tle)
    # 2. everything they could collide with
    group_tles, cache_meta = cache.get_tles(group=p.group, fetch_fn=engine.fetch_many, return_meta=True)
    # one TLE per object; the watchlist's copy wins so a satellite is never in there twice
    merged = {}
    for t in group_tles:
        nid = _norad(t)
        if nid is not None:
            merged[nid] = t
    merged.update(wl_tles)
    all_tles = list(merged.values())
    svc.check_work(len(all_tles), p.hours, p.step_seconds)

    # 3. can each satellite actually be propagated? (else "no alerts" would mislead)
    availability, focus = {}, set()
    for nid in ids:
        if nid in wl_errors:
            availability[nid] = {"status": "unavailable", "reason": f"TLE unavailable: {wl_errors[nid]}"}
            continue
        try:
            pos = engine.propagate(wl_tles[nid], ref)
            availability[nid] = {"status": "ok", "pos_name": pos["name"],
                                 "tle_status": pos["tle_status"], "tle_age_days": pos["tle_age_days"]}
            focus.add(nid)
        except Exception as exc:
            availability[nid] = {"status": "unavailable", "reason": str(exc)}

    out = {"conjunctions": [], "objects_checked": 0, "objects_unpropagatable": 0,
           "candidate_pairs": 0, "excluded_coorbiting_pairs": 0}
    if focus:
        out = conjw.find_conjunctions_in_window(
            all_tles, start=p.start_dt, hours=p.hours, threshold_km=p.threshold_km,
            step_seconds=p.step_seconds, include_coorbiting=p.include_coorbiting,
            focus_norad_ids=focus,
        )
    results = out["conjunctions"]
    if p.ml:
        results = ml_risk.score_conjunctions(results)
    staleness, _ = svc.annotate_tle_age(results, all_tles, ref)
    results.sort(key=lambda c: c["tca_utc"])          # an alert feed: soonest first
    return {"ref": ref, "results": results, "out": out, "staleness": staleness,
            "cache_meta": cache_meta, "availability": availability, "focus": focus}


def build_response(watched: list[dict], scr: dict | None, p: Params) -> dict:
    """One user's alert feed from a screening pass. `watched` = [{"norad_id", "name"}, ...]."""
    ref = scr["ref"] if scr else (p.start_dt or datetime.now(timezone.utc))
    base = {"window_start_utc": ref.isoformat(), "hours": p.hours, "threshold_km": p.threshold_km,
            "step_seconds": p.step_seconds, "group": p.group, "ml": p.ml,
            "watchlist_count": len(watched)}
    if not watched:
        return {**base, "satellites": [], "count": 0, "conjunctions": [],
                "warnings": ["Your watchlist is empty; add satellites with POST /watchlist"]}

    mine = {w["norad_id"] for w in watched}
    my_focus = mine & scr["focus"]
    sats = {}
    for w in watched:
        nid = w["norad_id"]
        a = scr["availability"].get(nid, {"status": "unavailable", "reason": "not screened"})
        entry = {"norad_id": nid, "name": w["name"], "status": a["status"], "alert_count": 0,
                 "closest_miss_km": None, "next_tca_utc": None, "highest_risk": None}
        if a["status"] == "ok":
            entry["name"] = entry["name"] or a["pos_name"]
            entry["tle_status"] = a["tle_status"]
            entry["tle_age_days"] = a["tle_age_days"]
        else:
            entry["reason"] = a["reason"]
        sats[nid] = entry

    conjunctions = []
    for c in scr["results"]:
        hits = [c[k]["norad_id"] for k in ("object_1", "object_2") if c[k]["norad_id"] in my_focus]
        if not hits:
            continue
        c = copy.deepcopy(c)                           # the pass is shared between users
        c["watched_norad_ids"] = hits
        conjunctions.append(c)
        for nid in hits:
            e = sats[nid]
            e["alert_count"] += 1
            if e["closest_miss_km"] is None or c["miss_distance_km"] < e["closest_miss_km"]:
                e["closest_miss_km"] = c["miss_distance_km"]
            if e["next_tca_utc"] is None or c["tca_utc"] < e["next_tca_utc"]:
                e["next_tca_utc"] = c["tca_utc"]
            if e["highest_risk"] is None or RISK_RANK[c["risk_level"]] > RISK_RANK[e["highest_risk"]]:
                e["highest_risk"] = c["risk_level"]

    out = scr["out"]
    warnings = svc.data_quality_warnings(scr["staleness"], out["objects_unpropagatable"], scr["cache_meta"])
    unavailable = [e for e in sats.values() if e["status"] == "unavailable"]
    if unavailable:
        warnings.append(f"{len(unavailable)} watched satellite(s) could not be checked; "
                        "see their reason in 'satellites'")
    unreliable = sum(1 for c in conjunctions if c.get("tle_status") == "unreliable")
    if unreliable:
        warnings.append(svc.unreliable_note(unreliable))

    return {
        **base,
        "satellites": list(sats.values()),
        "objects_checked": out["objects_checked"],
        "objects_unpropagatable": out["objects_unpropagatable"],
        "candidate_pairs": out["candidate_pairs"],
        "excluded_coorbiting_pairs": out["excluded_coorbiting_pairs"],
        "tle_staleness": scr["staleness"],
        "cache": scr["cache_meta"],
        "warnings": warnings,
        "count": len(conjunctions),
        "conjunctions": conjunctions,
    }
