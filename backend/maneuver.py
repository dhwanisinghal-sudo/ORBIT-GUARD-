"""
OrbitGuard - what-if maneuver (Week 7)
----------------------------------------
A real (impulsive) maneuver analysis:

  1. take the maneuvering satellite's SGP4 state at the burn time
  2. add a delta-v (given in the RTN frame: radial / along-track / cross-track)
  3. re-propagate with and without the burn, using the same two-body + J2 force model
  4. add the difference of those two runs to the satellite's SGP4 track
  5. screen the window for the time of closest approach (TCA) and miss distance,
     before and after the burn

Using the *difference* of two identical numerical runs cancels most of the mismatch between
SGP4 and our integrator, so the "before" numbers match the rest of the API (SGP4) exactly,
and only the effect of the burn is added on top. A zero delta-v gives identical before/after.

Limits (also reported to the caller): impulsive burn, J2 only (no drag / solar pressure
difference between the two runs), and SGP4's own TLE-age error applies to both objects.
It is a screening aid, not flight-dynamics-grade conjunction assessment.
"""

import math
from datetime import datetime, timedelta, timezone

import numpy as np
from scipy.integrate import solve_ivp
from sgp4.api import Satrec, WGS72, jday
from sgp4.earth_gravity import wgs72

import conjunction as conj
import orbit_engine as engine

MU = wgs72.mu                  # km^3/s^2 - same constants SGP4 itself uses
RE = wgs72.radiusearthkm       # km
J2 = wgs72.j2

MAX_HORIZON_HOURS = 72.0       # burn lead time + analysis window; TLE accuracy fades after ~3 days
MIN_STEP_S, MAX_STEP_S = 5.0, 120.0
MAX_DV_MS = 1000.0             # sanity cap on the total burn
REFINE_TOP_K = 12              # grid minima refined exactly (plus any within REFINE_BAND_KM of the best)
REFINE_BAND_KM = 15.0
MAX_REFINE = 40
MIN_FAST_REL_SPEED = 0.05      # km/s; slower pairs are "co-orbiting" and have no sharp TCA
CO_LOCATED_KM = 1.0            # pair already this close (and this slow) at `start`: docked / shared TLE


# ---------------------------------------------------------------- dynamics
def _deriv(_t, s):
    x, y, z, vx, vy, vz = s
    r2 = x * x + y * y + z * z
    r = math.sqrt(r2)
    g = -MU / (r2 * r)
    c = 1.5 * J2 * MU * RE * RE / (r2 * r2 * r)
    zz = 5.0 * z * z / r2
    return [vx, vy, vz,
            g * x + c * x * (zz - 1.0),
            g * y + c * y * (zz - 1.0),
            g * z + c * z * (zz - 3.0)]


def rtn_to_inertial(r: np.ndarray, v: np.ndarray, dv_rtn) -> np.ndarray:
    """RTN components -> inertial vector. +R radially outward, +T along the velocity direction
    (for a circular orbit), +N along the orbit normal (r x v)."""
    rh = r / np.linalg.norm(r)
    nh = np.cross(r, v)
    nh /= np.linalg.norm(nh)
    th = np.cross(nh, rh)
    return dv_rtn[0] * rh + dv_rtn[1] * th + dv_rtn[2] * nh


def semi_major_axis_km(r: np.ndarray, v: np.ndarray) -> float:
    return 1.0 / (2.0 / np.linalg.norm(r) - float(v @ v) / MU)


def along_track_dv_for_sma_change(r: np.ndarray, v: np.ndarray, delta_a_km: float) -> float:
    """Tangential delta-v (m/s) that changes the semi-major axis by delta_a_km (vis-viva)."""
    a = semi_major_axis_km(r, v)
    return MU * delta_a_km / (2.0 * a * a * float(np.linalg.norm(v))) * 1000.0


# ---------------------------------------------------------------- helpers
def _sat(tle: dict) -> Satrec:
    engine.validate_tle_format(tle)
    return Satrec.twoline2rv(tle["line1"], tle["line2"], WGS72)


def _grid_states(sat: Satrec, jd0: float, fr0: float, offsets: np.ndarray, name: str):
    err, r, v = sat.sgp4_array(np.full(len(offsets), jd0), fr0 + offsets / 86400.0)
    bad = np.flatnonzero(err != 0)
    if bad.size:
        code = int(err[bad[0]])
        raise engine.PropagationError(
            f"SGP4 propagation error code {code} ({engine.SGP4_ERRORS.get(code, 'unknown error')}) "
            f"for {name} at +{offsets[bad[0]] / 3600:.1f} h; the TLE is probably too far from its epoch",
            code=code)
    return r, v


def _sgp4_scalar(sat: Satrec, jd0: float, fr0: float, t: float, name: str):
    e, r, v = sat.sgp4(jd0, fr0 + t / 86400.0)
    if e != 0:
        raise engine.PropagationError(f"SGP4 propagation error code {e} for {name}", code=e)
    return np.array(r), np.array(v)


def _candidates(tau: np.ndarray, dr: np.ndarray, dv: np.ndarray) -> list[tuple[int, float]]:
    """Grid local minima of |dr|, ranked by a straight-line estimate of the true miss distance."""
    d = np.linalg.norm(dr, axis=1)
    left = np.r_[True, d[1:] <= d[:-1]]
    right = np.r_[d[:-1] <= d[1:], True]
    idx = np.flatnonzero(left & right)
    dd, vv = d[idx] ** 2, (dv[idx] ** 2).sum(axis=1)
    rdv = (dr[idx] * dv[idx]).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        est = np.where(np.sqrt(vv) >= MIN_FAST_REL_SPEED,
                       np.sqrt(np.maximum(dd - rdv ** 2 / vv, 0.0)), np.sqrt(dd))
    est = np.nan_to_num(est, nan=np.inf)
    order = np.argsort(est)
    best = est[order[0]]
    keep = [k for rank, k in enumerate(order) if rank < REFINE_TOP_K or est[k] <= best + REFINE_BAND_KM]
    return [(int(idx[k]), float(est[k])) for k in keep[:MAX_REFINE]]


def _refine(rel_state, lo: float, hi: float, s0: float):
    """Newton iteration on d/dt |dr|^2 = 0 using exact states, kept inside [lo, hi]."""
    s = min(max(s0, lo), hi)
    for _ in range(8):
        dr, dv = rel_state(s)
        vv = float(dv @ dv)
        if vv < 1e-12:
            break
        ds = -float(dr @ dv) / vv
        s = min(max(s + ds, lo), hi)
        if abs(ds) < 1e-3:
            break
    dr, dv = rel_state(s)
    return s, float(np.linalg.norm(dr)), float(np.linalg.norm(dv))


def _approaches(tau, dr_grid, dv_grid, rel_state, step, t0: datetime, limit=3) -> list[dict]:
    found = []
    for i, est in _candidates(tau, dr_grid, dv_grid):
        dr, dv = dr_grid[i], dv_grid[i]
        vv = float(dv @ dv)
        s0 = tau[i] + (-float(dr @ dv) / vv if math.sqrt(vv) >= MIN_FAST_REL_SPEED else 0.0)
        s, miss, rel = _refine(rel_state, max(tau[0], tau[i] - step), min(tau[-1], tau[i] + step), s0)
        found.append((s, miss, rel))
    found.sort(key=lambda f: f[1])
    out = []
    for s, miss, rel in found:
        if any(abs(s - o["_s"]) < 1.0 for o in out):
            continue
        out.append({"_s": s, "tca_utc": (t0 + timedelta(seconds=s)).isoformat(),
                    "miss_distance_km": round(miss, 3), "relative_speed_km_s": round(rel, 3)})
    return out[:limit]


def _summary(best: dict) -> dict:
    return {"tca_utc": best["tca_utc"], "distance_km": best["miss_distance_km"],
            "relative_speed_km_s": best["relative_speed_km_s"],
            "risk_level": conj._risk_level(best["miss_distance_km"])}


def make_burn_effect(r0: np.ndarray, v0: np.ndarray, dv_vec: np.ndarray, duration_s: float):
    """
    Returns f(t) -> change in the (x, y, z, vx, vy, vz) state, t seconds after the burn, caused by
    adding dv_vec (km/s, inertial) to the velocity at (r0, v0). t may be a scalar or an array of
    values in [0, duration_s]. Computed as (burned run) - (unburned run) with the same J2 model.
    """
    if not np.any(dv_vec):
        return lambda t: np.zeros((6,) + np.shape(t))
    y0 = np.hstack([r0, v0])
    kw = dict(method="DOP853", rtol=1e-9, atol=1e-9, dense_output=True)
    base = solve_ivp(_deriv, (0.0, duration_s), y0, **kw)
    burned = solve_ivp(_deriv, (0.0, duration_s), y0 + np.hstack([np.zeros(3), dv_vec]), **kw)
    if not (base.success and burned.success):
        raise RuntimeError("numerical propagation of the maneuver failed")
    return lambda t: burned.sol(t) - base.sol(t)


# ---------------------------------------------------------------- main entry point
def analyze_maneuver(tle_a: dict, tle_b: dict, *, dv_radial_ms: float = 0.0, dv_along_ms: float = 0.0,
                     dv_cross_ms: float = 0.0, altitude_delta_km: float | None = None,
                     burn_in_hours: float = 0.0, window_hours: float = 24.0,
                     start: datetime | None = None, step_seconds: float = 20.0) -> dict:
    """
    Apply an impulsive burn to object A and report how its closest approach to object B changes.

    The burn happens burn_in_hours after `start` (default: now); the pair is screened from
    `start` until burn_in_hours + window_hours. altitude_delta_km is the legacy input: it is
    converted into the along-track burn that changes the semi-major axis by that amount.
    """
    if not (0 <= burn_in_hours) or not (0 < window_hours):
        raise ValueError("burn_in_hours must be >= 0 and window_hours must be > 0")
    if burn_in_hours + window_hours > MAX_HORIZON_HOURS:
        raise ValueError(f"burn_in_hours + window_hours must be <= {MAX_HORIZON_HOURS:g}")
    if not (MIN_STEP_S <= step_seconds <= MAX_STEP_S):
        raise ValueError(f"step_seconds must be between {MIN_STEP_S:g} and {MAX_STEP_S:g}")
    if not all(math.isfinite(x) for x in (dv_radial_ms, dv_along_ms, dv_cross_ms)):
        raise ValueError("delta-v components must be finite numbers")

    sat_a, sat_b = _sat(tle_a), _sat(tle_b)
    start = engine._as_utc(start or datetime.now(timezone.utc))
    jd0, fr0 = jday(start.year, start.month, start.day, start.hour, start.minute,
                    start.second + start.microsecond / 1e6)

    t_burn = burn_in_hours * 3600.0
    horizon = t_burn + window_hours * 3600.0
    tau = np.append(np.arange(0.0, horizon, step_seconds), horizon)

    ra, va = _grid_states(sat_a, jd0, fr0, tau, tle_a["name"])
    rb, vb = _grid_states(sat_b, jd0, fr0, tau, tle_b["name"])

    # --- the burn
    r_burn, v_burn = _sgp4_scalar(sat_a, jd0, fr0, t_burn, tle_a["name"])
    legacy = altitude_delta_km is not None
    if legacy:
        dv_along_ms = along_track_dv_for_sma_change(r_burn, v_burn, altitude_delta_km)
    dv_vec = rtn_to_inertial(r_burn, v_burn,
                             np.array([dv_radial_ms, dv_along_ms, dv_cross_ms]) / 1000.0)
    dv_total_ms = float(np.linalg.norm(dv_vec) * 1000.0)
    if dv_total_ms > MAX_DV_MS:
        raise ValueError(f"total delta-v is {dv_total_ms:.0f} m/s; the limit is {MAX_DV_MS:g} m/s")

    burn_effect = make_burn_effect(r_burn, v_burn, dv_vec, horizon - t_burn)

    # --- grid, before and after
    ra2, va2 = ra.copy(), va.copy()
    post = tau >= t_burn
    if post.any():
        eff = burn_effect(tau[post] - t_burn)
        ra2[post] += eff[:3].T
        va2[post] += eff[3:].T

    def rel_before(t):
        a = _sgp4_scalar(sat_a, jd0, fr0, t, tle_a["name"])
        b = _sgp4_scalar(sat_b, jd0, fr0, t, tle_b["name"])
        return a[0] - b[0], a[1] - b[1]

    def rel_after(t):
        a_r, a_v = _sgp4_scalar(sat_a, jd0, fr0, t, tle_a["name"])
        if t >= t_burn:
            e = burn_effect(t - t_burn)
            a_r, a_v = a_r + e[:3], a_v + e[3:]
        b = _sgp4_scalar(sat_b, jd0, fr0, t, tle_b["name"])
        return a_r - b[0], a_v - b[1]

    before_list = _approaches(tau, ra - rb, va - vb, rel_before, step_seconds, start)
    after_list = _approaches(tau, ra2 - rb, va2 - vb, rel_after, step_seconds, start)
    orig = before_list[0]
    dist_at_orig = float(np.linalg.norm(rel_after(orig["_s"])[0]))

    notes = []

    # Docked / co-located pair (e.g. a cargo ship attached to a station, or two objects sharing one
    # TLE): the separation is ~0 at the start, so the "closest approach" is the start instant,
    # which the burn cannot change. Flag it and report how far the burn pushes the pair apart.
    sep0 = float(np.linalg.norm(ra[0] - rb[0]))
    relspeed0 = float(np.linalg.norm(va[0] - vb[0]))
    co_located = sep0 < CO_LOCATED_KM and relspeed0 < MIN_FAST_REL_SPEED
    d_before_post = np.linalg.norm((ra - rb)[post], axis=1) if post.any() else np.zeros(1)
    d_after_post = np.linalg.norm((ra2 - rb)[post], axis=1) if post.any() else np.zeros(1)
    if co_located:
        notes.append(
            f"These two objects are co-located at the start ({sep0:.3f} km apart, "
            f"{relspeed0:.4f} km/s relative speed) - typically docked, or sharing the same orbital data - "
            "so the closest approach is the starting instant and a burn cannot change it. Look at "
            "post_burn_separation_km to see how far the burn moves them apart, or pick a pair that "
            "actually has a future conjunction.")
    if orig["_s"] < t_burn:
        notes.append("The closest approach in this window happens before the burn, so the burn "
                     "cannot change it; try a smaller burn_in_hours.")
    if abs(after_list[0]["_s"] - orig["_s"]) > 60.0 and after_list[0]["miss_distance_km"] < orig["miss_distance_km"]:
        notes.append("After the burn the closest approach in the window is a different encounter from the "
                     "original one, and it is closer.")

    clean = lambda lst: [{k: v for k, v in e.items() if k != "_s"} for e in lst]
    return {
        "maneuver": {
            "burn_time_utc": (start + timedelta(seconds=t_burn)).isoformat(),
            "burn_in_hours": burn_in_hours,
            "dv_rtn_ms": {"radial": round(dv_radial_ms, 4), "along_track": round(dv_along_ms, 4),
                          "cross_track": round(dv_cross_ms, 4)},
            "dv_total_ms": round(dv_total_ms, 4),
            "semi_major_axis_km_before_burn": round(semi_major_axis_km(r_burn, v_burn), 3),
        },
        "window": {"start_utc": start.isoformat(), "end_utc": (start + timedelta(seconds=horizon)).isoformat(),
                   "hours": round(horizon / 3600.0, 3), "step_seconds": step_seconds},
        "before": {**_summary(before_list[0]), **({"risk_level": "DOCKED"} if co_located else {})},
        "after": {**_summary(after_list[0]), "distance_at_original_tca_km": round(dist_at_orig, 3),
                  **({"risk_level": "DOCKED"} if co_located else {})},
        "miss_distance_change_km": round(after_list[0]["miss_distance_km"] - orig["miss_distance_km"], 3),
        "closest_approaches": {"before": clean(before_list), "after": clean(after_list)},
        "scenario": {"co_located_at_start": co_located, "initial_separation_km": round(sep0, 3),
                     "initial_relative_speed_km_s": round(relspeed0, 4)},
        "post_burn_separation_km": {
            "before": {"at_window_end": round(float(d_before_post[-1]), 3), "max": round(float(d_before_post.max()), 3)},
            "after": {"at_window_end": round(float(d_after_post[-1]), 3), "max": round(float(d_after_post.max()), 3)},
        },
        "deprecation": ("altitude_delta_km is deprecated: it was converted to the along-track burn that "
                        "changes the semi-major axis by that amount. Use dv_along_ms / dv_radial_ms / "
                        "dv_cross_ms instead.") if legacy else None,
        "model": "SGP4 baseline + two-body/J2 numerical delta; impulsive burn; no drag or SRP in the delta",
        "notes": notes,
    }
