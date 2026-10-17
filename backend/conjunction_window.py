"""
OrbitGuard - time-window conjunction screening (step 2)
--------------------------------------------------------
conjunction.py only compares positions at ONE instant ("right now"), so two
satellites that pass 1 km apart ten minutes from now are never reported.

This module scans a whole time window (e.g. the next 24 h) and reports, for each
close-approaching pair, the TIME OF CLOSEST APPROACH (TCA) and the MISS DISTANCE
at that moment - which is what a real conjunction screening produces.

How it works (3 stages):

  1. Coarse screening. Propagate every object on a regular grid (default every
     60 s, vectorised with sgp4's SatrecArray) and, at each grid step, use a
     KDTree to find pairs closer than a "screening radius". The radius is the
     alert threshold plus the farthest two objects can close in half a step at
     the highest possible LEO relative speed (~16 km/s), so a pair that comes
     within `threshold_km` between two grid points is never missed. Each such
     pair is then tested with a straight-line estimate of its closest approach
     (from relative position and velocity); pairs that clearly won't come near
     are dropped immediately, which shrinks the candidate list by orders of
     magnitude on a real catalog.

  2. Candidate selection. For each surviving pair, find local minima of the
     distance-vs-time curve on the grid, and re-apply the straight-line test at
     each minimum.

  3. TCA refinement. For the few survivors, a short Newton iteration with the
     exact SGP4 states pins the TCA down to ~1 ms and gives the true miss
     distance and relative velocity.

Co-orbiting objects (e.g. a visiting vehicle docked to the ISS) sit within a
few metres of each other forever and have ~0 relative speed. They are not
conjunctions, so they are excluded unless include_coorbiting=True.

Accuracy note: SGP4/TLE positions are only good to roughly a kilometre near the
TLE epoch and degrade by several km per day, so treat results as screening
output, not a manoeuvre decision. Objects whose TLE fails to propagate are
skipped and counted in the result.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
from scipy.spatial import cKDTree
from sgp4.api import Satrec, SatrecArray, WGS72, jday

from conjunction import _risk_level

MAX_REL_SPEED_KM_S = 16.0     # head-on LEO is ~15.5 km/s
LINEAR_MARGIN_KM = 10.0       # flat slack on the straight-line miss estimate
# Orbit curvature bends the true relative path away from a straight line. Two nearby
# objects feel almost the same gravity; the difference ("tidal" term) is at most
# ~2*mu/r^3 * separation, so over s seconds the straight-line error is bounded by
# 0.5 * 2*mu/r^3 * separation * s^2  (mu/r^3 ~ 1.25e-6 /s^2 at LEO radii).
TIDAL_COEF = 1.25e-6
MIN_STEP_S, MAX_STEP_S = 10.0, 300.0
MAX_WINDOW_HOURS = 72.0       # TLE accuracy is poor beyond ~3 days
DEFAULT_MIN_REL_SPEED = 0.1   # km/s; below this a pair is "co-orbiting"
_TIME_CHUNK = 120             # grid steps propagated at once (bounds memory)
_PAIR_CHUNK = 2000            # pairs examined at once


def _jd_fr(when: datetime) -> tuple[float, float]:
    return jday(when.year, when.month, when.day, when.hour, when.minute,
                when.second + when.microsecond / 1e6)


def _linear_screen(dr: np.ndarray, dv: np.ndarray, threshold_km: float, min_rel: float):
    """
    Straight-line closest-approach estimate for many pairs at once.

    dr, dv: (n, 3) relative position (km) and velocity (km/s) at some instant.
    Returns (rel_speed, s_rel, miss_lin, plausible):
      s_rel      seconds from this instant to the estimated closest approach
      miss_lin   estimated miss distance there (km)
      plausible  True where the pair is moving fast enough to be a real
                 crossing AND could still come within threshold after allowing
                 for the curvature error bound above
    """
    dd = (dr * dr).sum(axis=1)
    vv = (dv * dv).sum(axis=1)
    rdv = (dr * dv).sum(axis=1)
    rel = np.sqrt(vv)
    fast = (vv > 1e-12) & (rel >= min_rel)
    with np.errstate(divide="ignore", invalid="ignore"):
        s_rel = -rdv / vv
        miss_lin = np.sqrt(np.maximum(dd - rdv ** 2 / vv, 0.0))
        margin = LINEAR_MARGIN_KM + TIDAL_COEF * np.sqrt(dd) * s_rel ** 2
        plausible = fast & (miss_lin <= threshold_km + margin)
    return rel, s_rel, miss_lin, np.nan_to_num(plausible, nan=False).astype(bool)


def _state(sat: Satrec, jd: float, fr: float, offset_s: float):
    """Position (km) and velocity (km/s) of one satellite, or None if SGP4 errors."""
    e, r, v = sat.sgp4(jd, fr + offset_s / 86400.0)
    if e != 0:
        return None
    return np.array(r), np.array(v)


def _refine_tca(sat_a: Satrec, sat_b: Satrec, jd: float, fr: float, s0: float):
    """
    Newton iteration on d/dt |r_a - r_b|^2 = 0 using exact SGP4 states.
    Returns (offset_seconds, miss_km, rel_speed_km_s, alt_a_km, alt_b_km) or None.
    """
    s = s0
    for _ in range(6):
        a, b = _state(sat_a, jd, fr, s), _state(sat_b, jd, fr, s)
        if a is None or b is None:
            return None
        dr, dv = a[0] - b[0], a[1] - b[1]
        vv = float(dv @ dv)
        if vv < 1e-12:
            break
        ds = -float(dr @ dv) / vv
        s += ds
        if abs(ds) < 1e-3:
            break

    a, b = _state(sat_a, jd, fr, s), _state(sat_b, jd, fr, s)
    if a is None or b is None:
        return None
    miss = float(np.linalg.norm(a[0] - b[0]))
    rel_speed = float(np.linalg.norm(a[1] - b[1]))
    return (s, miss, rel_speed,
            float(np.linalg.norm(a[0]) - 6371.0), float(np.linalg.norm(b[0]) - 6371.0))


def find_conjunctions_in_window(
    tles: list[dict],
    start: datetime | None = None,
    hours: float = 24.0,
    threshold_km: float = 5.0,
    step_seconds: float = 60.0,
    min_relative_speed_km_s: float = DEFAULT_MIN_REL_SPEED,
    include_coorbiting: bool = False,
) -> dict:
    """
    Screen `tles` for close approaches between `start` and `start + hours`.

    Returns a dict with the conjunctions (sorted by miss distance, closest first)
    plus stats about what was screened.
    """
    if not (0 < hours <= MAX_WINDOW_HOURS):
        raise ValueError(f"hours must be > 0 and <= {MAX_WINDOW_HOURS:g}")
    if not (MIN_STEP_S <= step_seconds <= MAX_STEP_S):
        raise ValueError(f"step_seconds must be between {MIN_STEP_S:g} and {MAX_STEP_S:g}")
    if threshold_km <= 0:
        raise ValueError("threshold_km must be > 0")

    start = start or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)

    # --- parse TLEs, skipping malformed ones ---
    sats, meta, malformed = [], [], 0
    for t in tles:
        try:
            # build both first: a failure must not leave sats and meta out of step
            sat = Satrec.twoline2rv(t["line1"], t["line2"], WGS72)
            info = {"name": t["name"], "norad_id": int(t["line1"][2:7])}
        except Exception:
            malformed += 1
            continue
        sats.append(sat)
        meta.append(info)
    n = len(sats)

    total_s = hours * 3600.0
    secs = np.arange(0.0, total_s, step_seconds)
    secs = np.append(secs, total_s)                      # always include the window end
    n_steps = len(secs)
    jd0, fr0 = _jd_fr(start)
    jd_grid = np.full(n_steps, jd0)
    fr_grid = fr0 + secs / 86400.0

    stats = {
        "objects_checked": 0,
        "objects_unpropagatable": malformed,
        "time_steps": n_steps,
        "candidate_pairs": 0,
        "excluded_coorbiting_pairs": 0,
    }
    result = {"conjunctions": [], **stats}
    if n < 2:
        result["objects_checked"] = n
        return result

    # ---------- stage 1: coarse screening on the time grid ----------
    screen_radius = threshold_km + MAX_REL_SPEED_KM_S * step_seconds / 2.0
    sat_array = SatrecArray(sats)
    pairs: set[tuple[int, int]] = set()        # pairs that might genuinely cross
    coorb: set[tuple[int, int]] = set()        # slow, close pairs (formation flight / docked)
    ever_valid = np.zeros(n, dtype=bool)

    for c0 in range(0, n_steps, _TIME_CHUNK):
        sl = slice(c0, c0 + _TIME_CHUNK)
        e, r, v = sat_array.sgp4(jd_grid[sl], fr_grid[sl])
        ok = (e == 0) & np.isfinite(r).all(axis=2)
        ever_valid |= ok.any(axis=1)
        for t in range(r.shape[1]):
            idx = np.nonzero(ok[:, t])[0]
            if idx.size < 2:
                continue
            pts, vel = r[idx, t, :], v[idx, t, :]
            found = cKDTree(pts).query_pairs(screen_radius, output_type="ndarray")
            if not found.size:
                continue
            dr = pts[found[:, 0]] - pts[found[:, 1]]
            dv = vel[found[:, 0]] - vel[found[:, 1]]
            rel, s_rel, _miss, plausible = _linear_screen(dr, dv, threshold_km, min_relative_speed_km_s)

            # keep only pairs whose estimated closest approach is near this grid point
            # (the grid point nearest the true TCA is always within half a step)
            keep = plausible & (np.abs(s_rel) <= step_seconds)
            if keep.any():
                pairs.update(map(tuple, idx[found[keep]].tolist()))

            slow = (rel < min_relative_speed_km_s) & (np.linalg.norm(dr, axis=1) <= threshold_km)
            if slow.any():
                coorb.update(map(tuple, idx[found[slow]].tolist()))

    result["objects_checked"] = int(ever_valid.sum())
    result["objects_unpropagatable"] = malformed + int(n - ever_valid.sum())
    result["candidate_pairs"] = len(pairs)
    result["excluded_coorbiting_pairs"] = 0 if include_coorbiting else len(coorb)
    if include_coorbiting:
        pairs |= coorb
    if not pairs:
        return result

    # ---------- stage 2: distance curves for candidate pairs only ----------
    pair_arr = np.array(sorted(pairs))
    involved = np.unique(pair_arr)
    local = np.searchsorted(involved, pair_arr)          # pair indices into `involved`
    sub = SatrecArray([sats[i] for i in involved])

    R_parts, V_parts = [], []
    for c0 in range(0, n_steps, _TIME_CHUNK):
        sl = slice(c0, c0 + _TIME_CHUNK)
        e, r, v = sub.sgp4(jd_grid[sl], fr_grid[sl])
        bad = (e != 0) | ~np.isfinite(r).all(axis=2)
        r[bad] = np.nan
        v[bad] = np.nan
        R_parts.append(r.astype(np.float32))
        V_parts.append(v.astype(np.float32))
    R = np.concatenate(R_parts, axis=1)                  # (involved, steps, 3)
    V = np.concatenate(V_parts, axis=1)
    del R_parts, V_parts

    events = []          # normal conjunctions awaiting refinement: (i, j, s_estimate)
    coorbiting = {}      # (i, j) -> (miss_km, step_index)  best coarse minimum per pair

    for p0 in range(0, len(local), _PAIR_CHUNK):
        pc = local[p0:p0 + _PAIR_CHUNK]
        D = np.linalg.norm(R[pc[:, 0]] - R[pc[:, 1]], axis=2)        # (pairs, steps)

        mask = np.zeros(D.shape, dtype=bool)                          # grid-local minima
        mask[:, 1:-1] = (D[:, 1:-1] < D[:, :-2]) & (D[:, 1:-1] <= D[:, 2:])
        mask[:, 0] = D[:, 0] <= D[:, 1]
        mask[:, -1] = D[:, -1] < D[:, -2]
        mask &= np.isfinite(D)
        pi, ki = np.nonzero(mask)
        if pi.size == 0:
            continue

        ia, ib = pc[pi, 0], pc[pi, 1]
        dr = (R[ia, ki] - R[ib, ki]).astype(np.float64)
        dv = (V[ia, ki] - V[ib, ki]).astype(np.float64)
        rel, s_rel, miss_lin, plausible = _linear_screen(dr, dv, threshold_km, min_relative_speed_km_s)

        if include_coorbiting:
            for q in np.nonzero(rel < min_relative_speed_km_s)[0]:
                miss = float(np.linalg.norm(dr[q]))
                if miss <= threshold_km:
                    key = (int(involved[ia[q]]), int(involved[ib[q]]))
                    if key not in coorbiting or miss < coorbiting[key][0]:
                        coorbiting[key] = (miss, int(ki[q]))

        s_est = secs[ki] + s_rel
        keep = plausible & (s_est >= -1.0) & (s_est <= total_s + 1.0)   # TCA inside the window
        for q in np.nonzero(keep)[0]:
            events.append((int(involved[ia[q]]), int(involved[ib[q]]), float(s_est[q])))

    # ---------- stage 3: refine TCA with exact SGP4 ----------
    refined = []
    for i, j, s_est in events:
        out = _refine_tca(sats[i], sats[j], jd0, fr0, s_est)
        if out is None:
            continue
        s, miss, rel_speed, alt_a, alt_b = out
        if miss <= threshold_km and -1.0 <= s <= total_s + 1.0 and rel_speed >= min_relative_speed_km_s:
            refined.append((i, j, s, miss, rel_speed, alt_a, alt_b, False))

    # co-orbiting pairs (only when requested): one event per pair
    for (i, j), (miss, k) in coorbiting.items():
        a, b = _state(sats[i], jd0, fr0, secs[k]), _state(sats[j], jd0, fr0, secs[k])
        if a is None or b is None:
            continue
        refined.append((i, j, float(secs[k]), float(np.linalg.norm(a[0] - b[0])),
                        float(np.linalg.norm(a[1] - b[1])),
                        float(np.linalg.norm(a[0]) - 6371.0), float(np.linalg.norm(b[0]) - 6371.0), True))

    # a pair can be found from two neighbouring grid minima: keep the closer one
    refined.sort(key=lambda x: (x[0], x[1], x[2]))
    deduped = []
    for ev in refined:
        if deduped and deduped[-1][:2] == ev[:2] and ev[2] - deduped[-1][2] < 2 * step_seconds:
            if ev[3] < deduped[-1][3]:
                deduped[-1] = ev
            continue
        deduped.append(ev)

    conjunctions = []
    for i, j, s, miss, rel_speed, alt_a, alt_b, co in deduped:
        tca = start + timedelta(seconds=s)
        conjunctions.append({
            "object_1": meta[i],
            "object_2": meta[j],
            "tca_utc": tca.isoformat(),
            "hours_from_start": round(s / 3600.0, 4),
            "miss_distance_km": round(miss, 3),
            "distance_km": round(miss, 3),            # same value; the ML scorer and old UI read this key
            "relative_velocity_km_s": round(rel_speed, 3),
            "altitude_km": {"object_1": round(alt_a, 2), "object_2": round(alt_b, 2)},
            "risk_level": _risk_level(miss),
            "co_orbiting": co,
        })
    conjunctions.sort(key=lambda c: (c["miss_distance_km"], c["tca_utc"]))

    result["conjunctions"] = conjunctions
    return result

